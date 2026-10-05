"""Run a finite command with a deadline independent of the terminal tool.

Not for persistent servers: descendants are stopped even after normal exit.
Windows worker joins a kill-on-close Job before creating the actual command,
so a fast grandchild cannot escape the deadline through an assignment race.
Output uses files, never inherited terminal pipes. No shell interpolation.
"""
from __future__ import annotations

import argparse
import ctypes
import math
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path


def _kernel():
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL("kernel32",use_last_error=True)
    signatures = {
        "CreateJobObjectW":([ctypes.c_void_p,w.LPCWSTR],w.HANDLE),
        "OpenJobObjectW":([w.DWORD,w.BOOL,w.LPCWSTR],w.HANDLE),
        "SetInformationJobObject":([w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD],w.BOOL),
        "AssignProcessToJobObject":([w.HANDLE,w.HANDLE],w.BOOL),
        "TerminateJobObject":([w.HANDLE,w.UINT],w.BOOL),
        "QueryInformationJobObject":([w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.c_void_p],w.BOOL),
        "CloseHandle":([w.HANDLE],w.BOOL),
        "GetCurrentProcess":([],w.HANDLE),
        "GetModuleFileNameW":([w.HMODULE,w.LPWSTR,w.DWORD],w.DWORD),
        "CreateToolhelp32Snapshot":([w.DWORD,w.DWORD],w.HANDLE),
        "Process32FirstW":([w.HANDLE,ctypes.c_void_p],w.BOOL),
        "Process32NextW":([w.HANDLE,ctypes.c_void_p],w.BOOL),
        "OpenProcess":([w.DWORD,w.BOOL,w.DWORD],w.HANDLE),
        "IsProcessInJob":([w.HANDLE,w.HANDLE,ctypes.POINTER(w.BOOL)],w.BOOL),
        "TerminateProcess":([w.HANDLE,w.UINT],w.BOOL),
        "WaitForSingleObject":([w.HANDLE,w.DWORD],w.DWORD),
        "GetExitCodeProcess":([w.HANDLE,ctypes.POINTER(w.DWORD)],w.BOOL),
    }
    for name,(arguments,result) in signatures.items():
        function = getattr(kernel,name)
        function.argtypes = arguments
        function.restype = result
    return kernel


def _native_python(kernel) -> str:
    path = ctypes.create_unicode_buffer(32768)
    if not kernel.GetModuleFileNameW(None,path,len(path)):
        raise ctypes.WinError(ctypes.get_last_error())
    return path.value


def _adopt_descendants(kernel,job,root_pid):
    """Adopt brokered descendants before the leader's process handle closes.

    App Execution Aliases can escape normal Job inheritance. Verify the current
    parent ID through an opened process handle, not just a stale PID snapshot.
    Keep adopted handles alive until the full traversal completes.
    """
    from ctypes import wintypes as w
    class Entry(ctypes.Structure):
        _fields_ = [("size",w.DWORD),("usage",w.DWORD),("pid",w.DWORD),
                    ("heap",ctypes.c_size_t),("module",w.DWORD),("threads",w.DWORD),
                    ("parent",w.DWORD),("priority",w.LONG),("flags",w.DWORD),
                    ("exe",w.WCHAR*260)]
    class BasicInfo(ctypes.Structure):
        _fields_ = [("reserved",ctypes.c_void_p),("peb",ctypes.c_void_p),
                    ("reserved2",ctypes.c_void_p*2),("pid",ctypes.c_size_t),("parent",ctypes.c_size_t)]
    native = ctypes.WinDLL("ntdll")
    native.NtQueryInformationProcess.argtypes = [w.HANDLE,w.ULONG,ctypes.c_void_p,w.ULONG,ctypes.c_void_p]
    native.NtQueryInformationProcess.restype = w.LONG
    snapshot = kernel.CreateToolhelp32Snapshot(2,0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    processes = []
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        more = kernel.Process32FirstW(snapshot,ctypes.byref(entry))
        while more:
            processes.append((entry.pid,entry.parent))
            more = kernel.Process32NextW(snapshot,ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    owners = {root_pid}
    handles = []
    try:
        changed = True
        while changed:
            changed = False
            for pid,parent in processes:
                if pid in owners or parent not in owners:
                    continue
                handle = kernel.OpenProcess(0x101101,False,pid)
                if not handle:
                    continue # already exited or inaccessible; never widen scope
                info = BasicInfo()
                if (native.NtQueryInformationProcess(handle,0,ctypes.byref(info),ctypes.sizeof(info),None)!=0
                        or info.parent != parent):
                    kernel.CloseHandle(handle)
                    continue
                member = w.BOOL()
                checked = kernel.IsProcessInJob(handle,job,ctypes.byref(member))
                if not checked or (not member.value and not kernel.AssignProcessToJobObject(job,handle)):
                    # Broker/package Jobs may reject nesting. This is still a
                    # verified owned descendant with an open termination handle.
                    if not kernel.TerminateProcess(handle,124):
                        error = ctypes.get_last_error()
                        exit_code = w.DWORD()
                        if not kernel.GetExitCodeProcess(handle,ctypes.byref(exit_code)) or exit_code.value==259:
                            kernel.CloseHandle(handle)
                            raise ctypes.WinError(error)
                    kernel.WaitForSingleObject(handle,500)
                handles.append(handle)
                owners.add(pid)
                changed = True
    finally:
        for handle in handles:
            kernel.CloseHandle(handle)


def _create_job(kernel,name):
    from ctypes import wintypes as w
    class BasicLimits(ctypes.Structure):
        _fields_ = [("process_time",ctypes.c_longlong),("job_time",ctypes.c_longlong),
                    ("flags",w.DWORD),("min_working_set",ctypes.c_size_t),
                    ("max_working_set",ctypes.c_size_t),("active_processes",w.DWORD),
                    ("affinity",ctypes.c_size_t),("priority",w.DWORD),("scheduling",w.DWORD)]
    class IoCounters(ctypes.Structure):
        _fields_ = [(name,ctypes.c_ulonglong) for name in ("read_ops","write_ops","other_ops","read_bytes","write_bytes","other_bytes")]
    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("basic",BasicLimits),("io",IoCounters),("process_memory",ctypes.c_size_t),
                    ("job_memory",ctypes.c_size_t),("peak_process_memory",ctypes.c_size_t),
                    ("peak_job_memory",ctypes.c_size_t)]
    job = kernel.CreateJobObjectW(None,name)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(job,9,ctypes.byref(limits),ctypes.sizeof(limits)):
        error = ctypes.get_last_error()
        kernel.CloseHandle(job)
        raise ctypes.WinError(error)
    return job


def _stop_job(kernel,job):
    from ctypes import wintypes as w
    class Accounting(ctypes.Structure):
        _fields_ = [(name,ctypes.c_longlong) for name in ("user","system","period_user","period_system")]+[
            ("page_faults",w.DWORD),("total",w.DWORD),("active",w.DWORD),("terminated",w.DWORD)]
    kernel.TerminateJobObject(job,124)
    deadline = time.monotonic()+1.5
    while time.monotonic()<deadline:
        state = Accounting()
        if not kernel.QueryInformationJobObject(job,1,ctypes.byref(state),ctypes.sizeof(state),None) or not state.active:
            break
        time.sleep(0.02)
    kernel.CloseHandle(job)


def _worker(name: str,command: list[str]) -> int:
    kernel = _kernel()
    job = kernel.OpenJobObjectW(0x0001,False,name) # JOB_OBJECT_ASSIGN_PROCESS
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not kernel.AssignProcessToJobObject(job,kernel.GetCurrentProcess()):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        # While waiting, only the supervisor owns a Job handle. Its death must
        # trigger KILL_ON_JOB_CLOSE rather than leave a handle in this worker.
        kernel.CloseHandle(job)
    env = None
    executable = shutil.which(command[0]) or command[0]
    if os.path.exists(executable) and os.path.samefile(executable,sys.executable):
        command = [_native_python(kernel),*command[1:]]
        env = {**os.environ,"__PYVENV_LAUNCHER__":sys.executable}
    process = subprocess.Popen(command,stdin=subprocess.DEVNULL,close_fds=True,env=env,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    result = process.wait()
    job = kernel.OpenJobObjectW(0x0001,False,name)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        _adopt_descendants(kernel,job,process.pid)
        return result
    finally:
        kernel.CloseHandle(job)


def run(command: list[str],timeout: float) -> int:
    if not command or not math.isfinite(timeout) or timeout<=0:
        raise ValueError("A command and finite positive timeout are required")
    kernel = job = None
    process = None
    expired = False
    options = {"start_new_session":True} if os.name != "nt" else {
        "creationflags":subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    if os.name == "nt":
        kernel = _kernel()
        name = "Local\\GeomwrightBounded-"+uuid.uuid4().hex
        job = _create_job(kernel,name)
        # App Execution Aliases can broker a new interpreter outside the Job.
        # Launch the actual PE image, preserving venv via CPython's launcher env.
        invocation = [_native_python(kernel),str(Path(__file__).resolve()),"--worker",name,"--",*command]
        options["env"] = {**os.environ,"__PYVENV_LAUNCHER__":sys.executable}
    else:
        invocation = command
    directory = tempfile.mkdtemp(prefix="geomwright-command-")
    try:
        output_path = Path(directory)/"output.log"
        try:
            deadline = time.monotonic()+timeout
            with output_path.open("wb") as output:
                process = subprocess.Popen(invocation,stdin=subprocess.DEVNULL,stdout=output,
                                           stderr=subprocess.STDOUT,close_fds=True,**options)
            while process.poll() is None:
                if time.monotonic()>=deadline:
                    expired = True
                    break
                time.sleep(min(0.05,max(0,deadline-time.monotonic())))
        finally:
            # A completed leader can leave live descendants holding its streams.
            # Stop the owned tree on success as well; persistent servers use the
            # Studio --background launcher instead of this finite-command API.
            if kernel and job:
                if process is not None and process.poll() is None:
                    # Windows Store/venv redirectors can sit outside the worker's
                    # Job. Stop the still-live supervisor tree before its leader
                    # disappears, then terminate Job members as the second boundary.
                    try:
                        subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],
                                       stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL,timeout=2,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
                    except (OSError,subprocess.TimeoutExpired):
                        pass
                _stop_job(kernel,job)
            elif process is not None:
                try:
                    os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process is not None:
                if process.poll() is None:
                    process.kill()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
        with output_path.open("rb") as output:
            output.seek(0,2)
            size = output.tell()
            output.seek(max(0,size-16000))
            tail = output.read(16000).decode("utf-8",errors="replace")
        if size>16000:
            print("[command output truncated to last 16000 bytes]")
        if tail:
            print(tail,end="" if tail.endswith("\n") else "\n")
    finally:
        try:
            shutil.rmtree(directory)
        except OSError:
            # Never wait indefinitely for a delayed Windows file-handle release.
            print(f"Command output retained at {directory}",file=sys.stderr)
    if expired:
        print(f"Command deadline exceeded after {timeout:g}s; owned process tree stopped.",file=sys.stderr)
        return 124
    return process.returncode if process is not None else 1


def main() -> int:
    # A terminal, pytest capture and redirected log can have different codepages.
    # Never let printing a Cyrillic path hide the actual termination result.
    sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    sys.stderr.reconfigure(encoding="utf-8",errors="replace")
    if len(sys.argv)>3 and sys.argv[1]=="--worker":
        return _worker(sys.argv[2],sys.argv[4:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout",type=float,required=True)
    parser.add_argument("command",nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1]==["--"] else args.command
    try:
        return run(command,args.timeout)
    except (OSError,ValueError) as exc:
        print(str(exc),file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
