"""Native session selection. Never substitute an instance after CAD access."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
from uuid import uuid4

# API5 KompasObject interface from the bundled KOMPAS typelib. QueryInterface
# stays on this selected COM object; it is not a ProgID-based second attachment.
API5_APPLICATION_IID = "{E36BC97C-39D6-4402-9C25-C7008A217E02}"


def process_ids():
    if os.name != "nt":
        raise RuntimeError("CAD_SESSION_IDENTITY_UNAVAILABLE: native Windows session required")
    processes = (w.DWORD * 65536)()
    size = w.DWORD()
    enum = ctypes.WinDLL("psapi", use_last_error=True).EnumProcesses
    enum.argtypes = [ctypes.POINTER(w.DWORD), w.DWORD, ctypes.POINTER(w.DWORD)]
    enum.restype = w.BOOL
    if not enum(processes, ctypes.sizeof(processes), ctypes.byref(size)) or size.value >= ctypes.sizeof(processes):
        raise RuntimeError("CAD_SESSION_IDENTITY_UNAVAILABLE: cannot snapshot existing processes")
    return set(processes[:size.value // ctypes.sizeof(w.DWORD)])


def window_identity(app):
    if os.name != "nt":
        raise RuntimeError("CAD_SESSION_IDENTITY_UNAVAILABLE: native Windows session required")
    hwnd = int(app.MainWindowHandle) & 0xffffffff
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.IsWindowVisible.argtypes = [w.HWND]
    user.GetAncestor.argtypes = [w.HWND, w.UINT]
    user.GetAncestor.restype = w.HWND
    user.GetWindow.argtypes = [w.HWND, w.UINT]
    user.GetWindow.restype = w.HWND
    pid = w.DWORD()
    if not hwnd or not user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) or not pid.value:
        raise RuntimeError("CAD_SESSION_IDENTITY_UNAVAILABLE: main window does not identify a process")
    api_hwnd = hwnd
    hwnd = _presentation_window(hwnd, pid.value, user)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid.value)
    if not handle:
        raise RuntimeError("CAD_SESSION_IDENTITY_UNAVAILABLE: cannot inspect owning process")
    try:
        times = [w.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
            raise RuntimeError("CAD_SESSION_IDENTITY_UNAVAILABLE: cannot read process creation time")
        started = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    finally:
        kernel.CloseHandle(handle)
    return {"window_handle": hwnd, "process_id": pid.value, "process_started_at": started,
            "window_visible": bool(user.IsWindowVisible(hwnd)), "api_window_handle": api_hwnd}


def _presentation_window(hwnd, process_id, user):
    """Follow only native root/owner links within the same process.

    v23 MainWindowHandle can identify an invisible controller owned by the
    actual visible frame. Searching unrelated windows by PID is not selection.
    """
    visited = set()
    for unused in range(16):
        if hwnd in visited:
            raise RuntimeError("CAD_SESSION_IDENTITY_UNAVAILABLE: cyclic window ownership")
        visited.add(hwnd)
        root = user.GetAncestor(hwnd, 2) or hwnd
        candidate = root if root != hwnd else user.GetWindow(hwnd, 4)
        if not candidate:
            return int(hwnd)
        pid = w.DWORD()
        if not user.GetWindowThreadProcessId(candidate, ctypes.byref(pid)) or pid.value != process_id:
            raise RuntimeError("CAD_SESSION_IDENTITY_UNAVAILABLE: presentation window belongs to another process")
        hwnd = int(candidate)
    raise RuntimeError("CAD_SESSION_IDENTITY_UNAVAILABLE: excessive window ownership depth")


def visible_process_ids(reference_pid):
    """Detect other visible instances even when ROT exposes only one of them."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]

    def image(pid):
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = w.DWORD(len(buffer))
            return Path(buffer.value).name.casefold() if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) else None
        finally:
            kernel.CloseHandle(handle)

    reference = image(reference_pid)
    if not reference:
        raise RuntimeError("CAD_SESSION_IDENTITY_UNAVAILABLE: cannot identify application image")
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.IsWindowVisible.argtypes = [w.HWND]
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = [callback_type, w.LPARAM]
    found, checked = set(), {}

    @callback_type
    def collect(hwnd, unused):
        if user.IsWindowVisible(hwnd):
            pid = w.DWORD()
            user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in checked:
                checked[pid.value] = image(pid.value)
            if checked[pid.value] == reference:
                found.add(pid.value)
        return True

    if not user.EnumWindows(collect, 0):
        raise RuntimeError("CAD_SESSION_IDENTITY_UNAVAILABLE: cannot enumerate visible instances")
    return found


def _api7(raw, direct):
    if direct:
        return raw
    app = getattr(raw, "ksGetApplication7", None)
    if callable(app):
        app = app()
    if app is None or not hasattr(app, "Documents"):
        raise RuntimeError("CAD_SESSION_IDENTITY_UNAVAILABLE: active API5 controller has no API7 application")
    return app


def recovery_window_state(binding):
    """Bounded native observation, independent of COM and model geometry."""
    if os.name != "nt":
        return {"observed_clear": False, "blockers": ["native_windows_required"]}
    user = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = binding["window_handle"]
    for name in ("IsWindow", "IsWindowEnabled", "IsWindowVisible"):
        getattr(user, name).argtypes = [w.HWND]
        getattr(user, name).restype = w.BOOL
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.GetWindow.argtypes = [w.HWND, w.UINT]
    user.GetWindow.restype = w.HWND
    user.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    user.SendMessageTimeoutW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM,
                                        w.UINT, w.UINT, ctypes.POINTER(ctypes.c_size_t)]
    user.SendMessageTimeoutW.restype = ctypes.c_size_t
    blockers, dialogs = [], []
    pid = w.DWORD()
    if not user.IsWindow(hwnd) or not user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) or pid.value != binding["process_id"]:
        return {"observed_clear": False, "blockers": ["bound_window_unavailable"]}
    if not user.IsWindowEnabled(hwnd):
        blockers.append("main_window_disabled")
    result = ctypes.c_size_t()
    # WM_NULL + SMTO_BLOCK|SMTO_ABORTIFHUNG: bounded UI responsiveness only.
    if not user.SendMessageTimeoutW(hwnd, 0, 0, 0, 3, 500, ctypes.byref(result)):
        blockers.append("main_window_not_responding")
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = [callback_type, w.LPARAM]

    @callback_type
    def collect(candidate, unused):
        if candidate == hwnd or not user.IsWindowVisible(candidate):
            return True
        owner_pid = w.DWORD()
        user.GetWindowThreadProcessId(candidate, ctypes.byref(owner_pid))
        if owner_pid.value != binding["process_id"]:
            return True
        name = ctypes.create_unicode_buffer(128)
        user.GetClassNameW(candidate, name, len(name))
        if name.value == "#32770" and len(dialogs) < 10:
            dialogs.append(int(candidate))
        return True

    if not user.EnumWindows(collect, 0):
        blockers.append("window_enumeration_failed")
    if dialogs:
        blockers.append("visible_dialog")
    return {"observed_clear": not blockers, "blockers": blockers, "dialog_windows": dialogs}


class Documents:
    def __init__(self, raw, visible):
        self.raw, self.visible = raw, visible

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def __call__(self, *args):
        return self.raw(*args)

    def Add(self, document_type, visible=True):
        return self.raw.Add(document_type, self.visible)

    def Open(self, path, visible=True, read_only=False):
        return self.raw.Open(path, self.visible, read_only)


class Application:
    def __init__(self, raw, session):
        object.__setattr__(self, "raw", raw)
        object.__setattr__(self, "session", session)

    def __getattr__(self, name):
        if name == "Documents":
            return Documents(self.raw.Documents, self.session.mode == "interactive")
        return getattr(self.raw, name)

    def __setattr__(self, name, value):
        if name == "Visible" and bool(value) != (self.session.mode == "interactive"):
            raise RuntimeError("CAD_MODE_MISMATCH: application visibility cannot change the selected work mode")
        setattr(self.raw, name, value)


class Session:
    def __init__(self, context):
        if not isinstance(context, dict) or context.get("mode") not in ("interactive", "hidden"):
            raise RuntimeError("CAD_SESSION_POLICY_REQUIRED: reload the MCP/Studio host; legacy implicit session selection is disabled")
        self.context = dict(context)
        self.mode = context["mode"]
        self.path = Path(context["context_path"])
        self.raw = self.app = None
        self.api7_direct = False
        self.allow_explicit_close = False
        self.cad_effects_started = False
        self._check_context()

    def _check_context(self):
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        if stored.get("token") != self.context.get("token") or stored.get("mode") != self.mode:
            raise RuntimeError("CAD_MODE_MISMATCH: session policy changed; no CAD access permitted")

    def _bind(self, identity, owned):
        self._check_context()
        self.context["binding"] = {key: identity[key] for key in
                                   ("window_handle", "process_id", "process_started_at")}
        self.context["binding"]["owned"] = owned
        stored = {key: value for key, value in self.context.items() if key != "context_path"}
        temporary = self.path.with_suffix("." + uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(stored, ensure_ascii=True), encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def attach(self, client, diagnostic=False):
        if diagnostic and not self.context.get("binding"):
            raise RuntimeError("CAD_SESSION_IDENTITY_UNAVAILABLE: recovery needs an existing bound instance")
        if self.context.get("shutdown_requested"):
            raise RuntimeError("CAD_HIDDEN_SESSION_ACTIVE: owned shutdown pending; no automatic replacement session")
        if self.app is not None:
            expected = self.mode == "interactive"
            identity = window_identity(self.app.raw)
            binding = self.context.get("binding") or {}
            if any(identity.get(key) != binding.get(key) for key in
                   ("window_handle", "process_id", "process_started_at")):
                raise RuntimeError("CAD_SESSION_CHANGED: bound window changed during the operation")
            if bool(self.app.raw.Visible) != expected or identity["window_visible"] != expected:
                raise RuntimeError("CAD_MODE_MISMATCH: selected window visibility changed; no automatic hide/show permitted")
            return self.app
        binding = self.context.get("binding")
        candidates = {}
        discovery = []
        for progid, direct in (("KOMPAS.Application.5", False), ("KOMPAS.Application.7", True)):
            stage = "get_active_object"
            try:
                raw = client.GetActiveObject(progid)
                stage = "resolve_api7"
                app = _api7(raw, direct)
                stage = "window_identity"
                identity = window_identity(app)
                stage = "application_visibility"
                visible = bool(app.Visible)
                discovery.append({"progid": progid, "ok": True, "identity": identity,
                                  "application_visible": visible})
                candidates.setdefault(identity["window_handle"], (raw, app, direct, identity))
            except Exception as exc:
                discovery.append({"progid": progid, "ok": False, "stage": stage,
                                  "error_type": type(exc).__name__, "error": str(exc)[:700]})
                continue
        if binding:
            chosen = candidates.get(binding["window_handle"])
            if chosen is None or any(chosen[3].get(key) != binding.get(key) for key in
                                     ("window_handle", "process_id", "process_started_at")):
                raise RuntimeError("CAD_SESSION_CHANGED: bound window/process is unavailable; explicitly select a session, never fall back to another instance")
            if self.mode == "hidden" and binding.get("owned") is not True:
                raise RuntimeError("CAD_HIDDEN_SESSION_NOT_OWNED: refusing to use a user's instance")
        elif self.mode == "interactive":
            visible = [candidate for candidate in candidates.values()
                       if bool(candidate[1].Visible) and candidate[3]["window_visible"]]
            target = self.context.get("target_window_handle")
            if target is not None:
                visible = [candidate for candidate in visible if candidate[3]["window_handle"] == target]
            if len(visible) != 1:
                raise RuntimeError("CAD_SESSION_NOT_VISIBLE: select one registered visible KOMPAS window; no application was created or made visible | discovery="
                                   + json.dumps(discovery, ensure_ascii=True, separators=(",", ":")))
            chosen = visible[0]
            if target is None and visible_process_ids(chosen[3]["process_id"]) != {chosen[3]["process_id"]}:
                raise RuntimeError("CAD_SESSION_AMBIGUOUS: multiple visible instances; explicitly select the target window handle")
            self._bind(chosen[3], owned=False)
        else:
            # CoCreate is not proof of isolation: a multi-use COM server may
            # return an existing process. Check before changing visibility.
            existing = process_ids()
            self.cad_effects_started = True
            raw = client.DispatchEx("KOMPAS.Application.5")
            app = _api7(raw, False)
            identity = window_identity(app)
            if identity["process_id"] in existing:
                raise RuntimeError("CAD_HIDDEN_SESSION_NOT_ISOLATED: COM returned an existing process; it was not hidden or closed")
            chosen = raw, app, False, identity
            self._bind(identity, owned=True)
            app.Visible = False
        self.raw, raw_app, self.api7_direct, identity = chosen
        expected = self.mode == "interactive"
        if bool(raw_app.Visible) != expected or window_identity(raw_app)["window_visible"] != expected:
            raise RuntimeError("CAD_MODE_MISMATCH: selected application visibility changed; no automatic hide/show permitted")
        if self.api7_direct and hasattr(self.raw, "_oleobj_"):
            try:
                import pythoncom
                same_object_api5 = self.raw._oleobj_.QueryInterface(API5_APPLICATION_IID, pythoncom.IID_IDispatch)
                self.raw = client.Dispatch(same_object_api5)
            except Exception:
                # API5-only operations must then report unavailable. Never ask
                # ROT/Dispatch for another application's API5 controller.
                pass
        controller = getattr(self.raw, "ActivateControllerAPI", None)
        if callable(controller) and not diagnostic:
            self.cad_effects_started = True
            controller()
        if bool(raw_app.Visible) != expected or window_identity(raw_app)["window_visible"] != expected:
            raise RuntimeError("CAD_MODE_MISMATCH: controller activation changed application visibility; CAD action refused")
        self.cad_effects_started = True
        self.app = Application(raw_app, self)
        return self.app

    def audit_recovery(self, client, bridge):
        """Observe a completed request's instance; never create, activate or repair."""
        binding = self.context.get("binding") or {}
        report = {"ok": False, "session_observed_clear": False, "model_verified": False,
                  "documents_changed": False, "blockers": []}
        if not binding or (self.mode == "hidden" and binding.get("owned") is not True):
            report["blockers"].append("selected_session_not_bound")
            return report
        window = recovery_window_state(binding)
        report["window"] = window
        if not window["observed_clear"]:
            report["blockers"].extend(window["blockers"])
            return report
        app = self.attach(client, diagnostic=True)
        active = app.ActiveDocument
        doc2 = self.raw.ActiveDocument2D()
        doc3 = self.raw.ActiveDocument3D()
        if doc2 is not None:
            running = doc2.ksIsActiveProcessRunnig()
            if running != 0:
                report["blockers"].append("graphical_process_running_or_unknown")
            # An active graphical API5 document alongside a 3D document may be
            # its sketch editor. Do not EndEdit as a diagnostic side effect.
            if doc3 is not None:
                report["blockers"].append("possible_active_sketch_editor")
        if doc3 is not None and doc3.IsEditMode() != 0:
            report["blockers"].append("component_edit_mode")
        if active is not None and int(active.DocumentType) == 2:
            fragment = bridge._cast_to_com_interface(active, "IFragmentDocument")
            if fragment is None or fragment.IsSketch:
                report["blockers"].append("sketch_fragment_or_unknown_fragment")
        documents = app.Documents
        count = int(documents.Count)
        report["documents_count"] = count
        report["documents"] = [bridge.describe_document(documents.Item(index), app, index)
                               for index in range(min(count, 50))]
        report["documents_truncated"] = count > 50
        report["active_document"] = bridge.describe_document(active, app) if active is not None else None
        report["session_identity"] = dict(binding)
        # Recheck the native frame after getters, without sending a CAD command.
        window = recovery_window_state(binding)
        report["window"] = window
        report["blockers"].extend(window["blockers"])
        report["ok"] = report["session_observed_clear"] = not report["blockers"]
        return report

    def describe(self):
        return {"mode": self.mode, "binding": self.context.get("binding"),
                "window_verified": self.app is not None,
                "per_action_ui_animation_guaranteed": False}

    def quit_owned(self):
        if self.mode != "hidden" or not (self.context.get("binding") or {}).get("owned") or self.app is None:
            raise RuntimeError("CAD_HIDDEN_SESSION_NOT_OWNED: refusing application shutdown")
        self.attach(None)  # Revalidate the cached selected identity/visibility.
        if int(self.app.Documents.Count) != 0:
            raise RuntimeError("CAD_HIDDEN_SESSION_ACTIVE: documents remain; refusing application shutdown")
        if self.app.Quit() is False:
            raise RuntimeError("CAD_HIDDEN_SESSION_ACTIVE: owned application refused shutdown")
        # Quit acceptance is not proof of process exit. Retain ownership so the
        # host refuses replacement/rebinding until this process really exits.
        self.context["shutdown_requested"] = True
        self._check_context()
        stored = {key: value for key, value in self.context.items() if key != "context_path"}
        temporary = self.path.with_suffix("." + uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(stored, ensure_ascii=True), encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
