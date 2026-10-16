from __future__ import annotations

import hashlib
import os
from pathlib import Path
import threading
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates
except ModuleNotFoundError as exc:  # pragma: no cover - exercised by installation boundary
    raise RuntimeError("Geomwright Studio requires: pip install 'geomwright[ui]'") from exc

from pydantic import ValidationError

from .registry import get_module, list_modules, preview_module
from .registry import managed_pulley_plan
from .camshaft import CamshaftGeometryError, CamshaftPhasesRequest, cam_profile_request
from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.bridge_runner import DEFAULT_NORMAL_TIMEOUT_SECONDS
from kompas_mcp import cams
from kompas_mcp.cams.errors import CamSynthesisError


_ROOT = Path(__file__).resolve().parent
_TRUSTED_HOSTS = {"127.0.0.1", "localhost", "::1"}
_FINISHED_JOB_LIMIT = 100


def _http_authority(value: str, scheme: str) -> tuple[str, int]:
    """Parse a single HTTP authority without accepting URL syntax in Host."""
    parsed = urlsplit(f"{scheme}://{value}")
    if (scheme not in {"http", "https"} or not value or parsed.netloc != value or parsed.path
            or parsed.query or parsed.fragment or parsed.username is not None
            or parsed.password is not None or any(c.isspace() for c in value)
            or value.endswith(":") or "\\" in value):
        raise ValueError("Invalid HTTP authority")
    host = parsed.hostname
    port = parsed.port
    if host is None or (port is not None and not 1 <= port <= 65535):
        raise ValueError("Invalid HTTP authority")
    return host, port if port is not None else (443 if scheme == "https" else 80)


def _static_content_version() -> str:
    digest = hashlib.sha256()
    for path in sorted((_ROOT / "static").glob("*.css")) + sorted((_ROOT / "static").glob("*.js")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _studio_content_version() -> str:
    """Fingerprint the Studio source that a running process keeps in memory."""
    digest = hashlib.sha256()
    paths = (
        list(_ROOT.glob("*.py"))
        + list((_ROOT / "templates").glob("*.html"))
        + list((_ROOT / "static").glob("*.js"))
        + list((_ROOT / "static").glob("*.css"))
    )
    for path in sorted(paths):
        digest.update(path.relative_to(_ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    # A process also retains the cam calculation modules, not just the UI.
    # Otherwise a calculation-only fix can silently reuse an outdated server.
    for path in sorted(Path(cams.__file__).parent.glob("*.py")):
        digest.update(f"cams/{path.name}".encode("utf-8"))
        digest.update(path.read_bytes())
    # CAD plans and spline fitting are cached in this process too. A geometry-only
    # fix must not reuse a Studio instance with the old gear generator.
    from kompas_mcp import gears
    for path in sorted(Path(gears.__file__).parent.glob("*.py")):
        digest.update(f"gears/{path.name}".encode("utf-8"))
        digest.update(path.read_bytes())
    # Spline previews retain both calculation/catalog code and request schemas.
    # Hash the package tree so new helpers also invalidate an existing process.
    from kompas_mcp.connections import splines
    spline_root = Path(splines.__file__).parent
    for path in sorted(spline_root.rglob("*.py")):
        digest.update(f"connections/splines/{path.relative_to(spline_root).as_posix()}".encode("utf-8"))
        digest.update(path.read_bytes())
    # Managed creation finalizers live in the cached host adapter, not the bridge.
    from kompas_mcp import adapter as adapter_runtime
    digest.update(b"kompas_mcp/adapter.py")
    digest.update(Path(adapter_runtime.__file__).read_bytes())
    from kompas_mcp import bridge_runner as runner_runtime
    digest.update(b"kompas_mcp/bridge_runner.py")
    digest.update(Path(runner_runtime.__file__).read_bytes())
    from kompas_mcp import session_guard as guard_runtime
    digest.update(b"kompas_mcp/session_guard.py")
    digest.update(Path(guard_runtime.__file__).read_bytes())
    # Same source with a different launch environment must not reuse a server
    # whose cached adapters select the previous native interpreter.
    selected_python = os.environ.get("KOMPAS_PYTHON") or str(runner_runtime.default_kompas_python_path())
    digest.update(b"cad_python_selection")
    digest.update(str(Path(selected_python).resolve()).encode("utf-8"))
    from kompas_mcp.transmissions import silent_chain
    digest.update(b"transmissions/silent_chain.py")
    digest.update(Path(silent_chain.__file__).read_bytes())
    from kompas_mcp.transmissions import silent_geometry
    for path in sorted(Path(silent_geometry.__file__).parent.glob("*.py")):
        digest.update(f"transmissions/silent_geometry/{path.name}".encode("utf-8"))
        digest.update(path.read_bytes())
    from kompas_mcp.sketch_runtime import cubic
    digest.update(b"sketch_runtime/cubic.py")
    digest.update(Path(cubic.__file__).read_bytes())
    return digest.hexdigest()[:12]


def _validation_detail(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {
            "loc": list(error.get("loc") or []),
            "msg": str(error.get("msg") or "Invalid value"),
            "type": str(error.get("type") or "value_error"),
            "ctx": {key: value for key, value in (error.get("ctx") or {}).items()
                    if key in {"gt", "ge", "lt", "le"}},
        }
        for error in exc.errors()
    ]


def _pick_model_file() -> str | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilename(
            title="Open KOMPAS model",
            filetypes=[("KOMPAS 3D models", "*.m3d"), ("All files", "*.*")],
        )
        return str(selected) if selected else None
    finally:
        root.destroy()


def _pick_save_model_file(suggested_name: str = "model.m3d") -> str | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.asksaveasfilename(
            title="Save KOMPAS model",
            defaultextension=".m3d",
            initialfile=suggested_name,
            filetypes=[("KOMPAS 3D models", "*.m3d"), ("All files", "*.*")],
        )
        return str(selected) if selected else None
    finally:
        root.destroy()


def create_app(
    *,
    adapter_factory: Any = KompasAdapter,
    file_picker: Any = _pick_model_file,
    save_file_picker: Any = _pick_save_model_file,
) -> FastAPI:
    def studio_adapter(
        cancel_event: threading.Event | None = None,
        *,
        interruptible: bool = True,
    ) -> Any:
        adapter = adapter_factory()
        runner = getattr(adapter, "runner", None)
        if runner is not None:
            runner.require_visible_kompas = True
            runner.cad_mode = "interactive"
            runner.timeout_seconds = DEFAULT_NORMAL_TIMEOUT_SECONDS
            runner.cancel_event = cancel_event if interruptible else None
        return adapter

    app = FastAPI(
        title="Geomwright Studio",
        version="0.1.0",
        description="Local preview and managed KOMPAS build UI for registered Geomwright modules.",
    )
    templates = Jinja2Templates(directory=str(_ROOT / "templates"))
    static_version = _static_content_version()
    studio_version = _studio_content_version()
    app.mount("/static", StaticFiles(directory=str(_ROOT / "static")), name="static")

    @app.middleware("http")
    async def _local_http_boundary(request: Request, call_next):  # type: ignore[no-untyped-def]
        # CORS response headers do not prevent a foreign page from sending a
        # simple POST. Check before any route can invoke a picker or adapter.
        try:
            hosts = request.headers.getlist("host")
            if len(hosts) != 1:
                raise ValueError("A single Host is required")
            authority = _http_authority(hosts[0], request.url.scheme)
            if authority[0] not in _TRUSTED_HOSTS:
                raise ValueError("Untrusted Host")
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Untrusted or invalid Host"})
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origins = request.headers.getlist("origin")
            fetch_sites = request.headers.getlist("sec-fetch-site")
            valid = not origins and not any(key.startswith("sec-fetch-") for key in request.headers)
            if len(origins) == 1:
                try:
                    origin = urlsplit(origins[0])
                    valid = (origins[0] == f"{origin.scheme}://{origin.netloc}"
                             and origin.scheme == request.url.scheme
                             and not origin.path and not origin.query and not origin.fragment
                             and _http_authority(origin.netloc, origin.scheme) == authority)
                except ValueError:
                    valid = False
                if fetch_sites and fetch_sites not in (["same-origin"], ["none"]):
                    valid = False
            if not valid:
                return JSONResponse(status_code=403, content={"detail": "A same-origin request is required"})
        return await call_next(request)

    @app.middleware("http")
    async def _revalidate_static(request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response


    cad_jobs: dict[str, dict[str, Any]] = {}
    cad_jobs_lock = threading.Lock()
    cad_build_lock = threading.Lock()
    cad_cancel_events: dict[str, threading.Event] = {}

    def prune_finished_jobs() -> None:
        # Caller holds cad_jobs_lock; cancel events share the same lifetime.
        finished = sorted(
            (job for job in cad_jobs.values() if job["status"] in {"completed", "failed", "cancelled"}),
            key=lambda job: float(job.get("finished_at") or 0.0),
        )
        for job in finished[:-_FINISHED_JOB_LIMIT]:
            cad_jobs.pop(job["id"], None)
            cad_cancel_events.pop(job["id"], None)

    def submit_cad_job(target: Any, args: tuple[Any, ...]) -> dict[str, Any]:
        job_id = uuid4().hex
        with cad_jobs_lock:
            # The UI tracks one build. Refuse extra work before allocating a
            # thread; cancellation remains outstanding until the worker settles.
            if any(job["status"] in {"queued", "running"} for job in cad_jobs.values()):
                raise HTTPException(status_code=409, detail="A CAD job is already active; wait for it to finish")
            prune_finished_jobs()
            cad_jobs[job_id] = {
                "id": job_id, "status": "queued", "stage": "queued",
                "created_at": time.time(), "started_at": None,
                "finished_at": None, "result": None, "error": None,
            }
            cad_cancel_events[job_id] = threading.Event()
            try:
                threading.Thread(target=target, args=(job_id, *args),
                                 name=f"geomwright-cad-{job_id[:8]}", daemon=True).start()
            except Exception as exc:
                cad_jobs.pop(job_id, None)
                cad_cancel_events.pop(job_id, None)
                raise HTTPException(status_code=503, detail="Could not start the CAD worker") from exc
        return job_snapshot(job_id)

    def job_snapshot(job_id: str) -> dict[str, Any]:
        with cad_jobs_lock:
            job = cad_jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return dict(job)

    def update_job(job_id: str, **values: Any) -> None:
        with cad_jobs_lock:
            cad_jobs[job_id].update(values)
            prune_finished_jobs()

    def run_cad_job(job_id: str, module_kind: str, profile: dict[str, Any], name: str) -> None:
        cancel_event = cad_cancel_events[job_id]
        def report_bridge_progress(event: dict[str, Any]) -> None:
            update_job(
                job_id,
                stage="bridge_operation",
                progress={
                    "percent": int(event.get("percent") or 0),
                    "operation": str(event.get("operation") or "unknown"),
                    "name": str(event.get("name") or ""),
                    "names": [str(item) for item in list(event.get("names") or []) if item],
                },
            )

        try:
            with cad_build_lock:
                if cancel_event.is_set():
                    update_job(job_id, status="cancelled", stage="cancelled", finished_at=time.time())
                    return
                update_job(
                    job_id,
                    status="running",
                    stage="building_in_kompas",
                    started_at=time.time(),
                    progress={"percent": 0, "operation": "starting", "name": name, "names": []},
                )
                result = create_module(studio_adapter(cancel_event), module_kind, profile, name,
                                       progress_callback=report_bridge_progress)
                update_job(
                    job_id,
                    status="completed",
                    stage="verified",
                    finished_at=time.time(),
                    result=result,
                    progress={"percent": 100, "operation": "completed", "name": name, "names": []},
                )
        except Exception as exc:
            cancelled = cancel_event.is_set()
            update_job(
                job_id,
                status="cancelled" if cancelled else "failed",
                stage="cancelled" if cancelled else "failed",
                finished_at=time.time(),
                error=str(exc),
                partial_result=getattr(exc,"partial_result",None),
            )

    def create_module(adapter: Any, module_kind: str, profile: dict[str, Any], name: str,
                       progress_callback: Any = None) -> dict[str, Any]:
        if module_kind == "silent_chain_sprocket":
            plan = managed_pulley_plan(module_kind, profile)
            plan["name"] = name
            return adapter.create_silent_chain_sprocket(
                plan, execute=True, confirm_write=True, visible=True,
                progress_callback=progress_callback,
            )
        if module_kind == "gear_spur":
            plan = managed_pulley_plan(module_kind, profile)
            plan["name"] = name
            return adapter.create_gear_spur(
                plan, execute=True, confirm_write=True, visible=True,
                progress_callback=progress_callback,
            )
        if module_kind == "gear_internal":
            plan = managed_pulley_plan(module_kind, profile)
            plan["name"] = name
            return adapter.create_gear_internal(
                plan, execute=True, confirm_write=True, visible=True,
                progress_callback=progress_callback,
            )
        if module_kind == "gear_bevel":
            plan = managed_pulley_plan(module_kind, profile)
            plan["name"] = name
            return adapter.create_gear_bevel(
                plan, execute=True, confirm_write=True, visible=True,
                progress_callback=progress_callback,
            )
        if module_kind in ("shaft_spline", "hub_spline"):
            plan = managed_pulley_plan(module_kind, profile)
            plan["name"] = name
            return adapter.create_spline(
                plan, execute=True, confirm_write=True, visible=True,
                progress_callback=progress_callback,
            )
        if module_kind == "camshaft_lobe":
            request = CamshaftPhasesRequest.model_validate(profile)
            if request.step != "cam":
                raise ValueError("Open the Cam step to build the calculated cam profile")
            return adapter.create_cam(cam_profile_request(request),width=request.cam_width,
                                      rotation_deg=request.cam_rotation_deg,tolerance=request.cad_tolerance,
                                       name=name,execute=True,confirm_write=True,visible=True,
                                       progress_callback=progress_callback,studio_profile=request.model_dump(mode="json"))
        return adapter.create_managed_pulley(
                    family=module_kind,
                    profile_request=profile,
                    name=name,
                    execute=True,
                    confirm_write=True,
                    visible=True,
                    progress_callback=progress_callback,
                )

    def run_update_job(
        job_id: str,
        module_kind: str,
        profile: dict[str, Any],
        previous_profile: dict[str, Any],
        name: str,
        document_id: str,
        block_id: str,
    ) -> None:
        cancel_event = cad_cancel_events[job_id]
        def report_bridge_progress(event: dict[str, Any]) -> None:
            update_job(
                job_id,
                stage="bridge_operation",
                progress={
                    "percent": int(event.get("percent") or 0),
                    "operation": str(event.get("operation") or "unknown"),
                    "name": str(event.get("name") or ""),
                    "names": [str(item) for item in list(event.get("names") or []) if item],
                },
            )

        try:
            with cad_build_lock:
                if cancel_event.is_set():
                    update_job(job_id, status="cancelled", stage="cancelled", finished_at=time.time())
                    return
                update_job(
                    job_id,
                    status="running",
                    stage="updating_in_kompas",
                    started_at=time.time(),
                    progress={"percent": 0, "operation": "starting_update", "name": name, "names": []},
                )
                # Topology replacement deletes and recreates an owned CAD branch.  The
                # bridge must be allowed to finish its rollback if that transaction fails;
                # terminating its process here can leave the user's model half-deleted.
                result = studio_adapter(cancel_event, interruptible=False).update_managed_pulley(
                    document_id=document_id,
                    block_id=block_id,
                    family=module_kind,
                    profile_request=profile,
                    previous_profile_request=previous_profile,
                    name=name,
                    execute=True,
                    confirm_write=True,
                    progress_callback=report_bridge_progress,
                )
                update_job(
                    job_id,
                    status="completed",
                    stage="verified",
                    finished_at=time.time(),
                    result=result,
                    progress={"percent": 100, "operation": "updated", "name": name, "names": []},
                )
        except Exception as exc:
            cancelled = cancel_event.is_set()
            update_job(
                job_id,
                status="cancelled" if cancelled else "failed",
                stage="cancelled" if cancelled else "failed",
                finished_at=time.time(),
                error=str(exc),
            )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="base.html",
            context={"module_count": len(list_modules()), "static_version": static_version},
        )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "product": "geomwright_studio",
            "pid":os.getpid(),
            "launch_id":os.environ.get("GEOMWRIGHT_STUDIO_LAUNCH_ID"),
            "mode": "managed_cad",
            "contract_version": 2,
            "static_version": static_version,
            "studio_version": studio_version,
            "capabilities": [
                "managed_pulley_plan",
                "managed_pulley_create_job",
                "managed_pulley_update_job",
                "workspace_document_lifecycle",
            ],
            "module_count": len(list_modules()),
        }

    @app.get("/modules")
    def modules() -> dict[str, Any]:
        return {"items": list_modules(), "count": len(list_modules())}

    @app.get("/workspace")
    def workspace() -> dict[str, Any]:
        try:
            return studio_adapter().studio_workspace_snapshot()
        except RuntimeError as exc:
            message = str(exc)
            if "No running visible KOMPAS-3D instance" in message or "No running KOMPAS-3D instance" in message:
                return {"ok": False, "connected": False, "documents": [], "active_runtime_id": None, "diagnostic": message}
            raise HTTPException(status_code=502, detail=message) from exc

    @app.post("/workspace/open")
    def workspace_open(payload: dict[str, Any]) -> dict[str, Any]:
        path = str(payload.get("path") or "").strip()
        if not path:
            raise HTTPException(status_code=422, detail="path is required")
        try:
            adapter = studio_adapter()
            opened = adapter.open_document(path, visible=True, read_only=False)
            return {"ok": True, "opened": opened, "workspace": adapter.studio_workspace_snapshot()}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/workspace/open-dialog")
    def workspace_open_dialog() -> dict[str, Any]:
        try:
            path = file_picker()
            if not path:
                return {"ok": True, "cancelled": True}
            adapter = studio_adapter()
            opened = adapter.open_document(path, visible=True, read_only=False)
            return {"ok": True, "cancelled": False, "opened": opened, "workspace": adapter.studio_workspace_snapshot()}
        except (OSError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/workspace/pick-file")
    def workspace_pick_file() -> dict[str, Any]:
        try:
            path = file_picker()
            return {"ok": True, "cancelled": not bool(path), "path": path}
        except (OSError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/workspace/pick-save-file")
    def workspace_pick_save_file(payload: dict[str, Any]) -> dict[str, Any]:
        suggested_name = str(payload.get("suggested_name") or "model.m3d").strip()
        if not suggested_name.lower().endswith(".m3d"):
            suggested_name += ".m3d"
        try:
            path = save_file_picker(suggested_name)
            return {"ok": True, "cancelled": not bool(path), "path": path}
        except (OSError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/workspace/activate")
    def workspace_activate(payload: dict[str, Any]) -> dict[str, Any]:
        document_id = str(payload.get("document_id") or "").strip()
        if not document_id:
            raise HTTPException(status_code=422, detail="document_id is required")
        try:
            adapter = studio_adapter()
            activated = adapter.activate_document(document_id, strict=True)
            return {"ok": True, "activated": activated, "workspace": adapter.studio_workspace_snapshot()}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/workspace/close")
    def workspace_close(payload: dict[str, Any]) -> dict[str, Any]:
        document_id = str(payload.get("document_id") or "").strip()
        action = str(payload.get("action") or "").strip().lower()
        save_path = str(payload.get("save_path") or "").strip()
        if not document_id:
            raise HTTPException(status_code=422, detail="document_id is required")
        if action not in {"save", "discard"}:
            raise HTTPException(status_code=422, detail="action must be 'save' or 'discard'")
        try:
            adapter = studio_adapter()
            before = adapter.studio_workspace_snapshot()
            entry = next(
                (
                    item
                    for item in before.get("documents", [])
                    if item.get("document", {}).get("runtime_id") == document_id
                ),
                None,
            )
            if entry is None:
                raise ValueError("Document is no longer open; refresh the workspace")
            document = entry["document"]
            if action == "save":
                if document.get("path"):
                    closed = adapter.save_document(
                        document_id=document_id,
                        close_after_save=True,
                        strict=True,
                        user_requested_close=True,
                    )
                elif save_path:
                    closed = adapter.save_document_as(
                        save_path,
                        document_id=document_id,
                        close_after_save=True,
                        strict=True,
                        user_requested_close=True,
                    )
                else:
                    raise ValueError("save_path is required for an unsaved document")
            else:
                closed = adapter.close_document(
                    document_id=document_id,
                    save=False,
                    close_mode=0,
                    strict=True,
                    user_requested=True,
                )
            return {
                "ok": True,
                "action": action,
                "closed": closed,
                "workspace": adapter.studio_workspace_snapshot(),
            }
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/workspace/save")
    def workspace_save(payload: dict[str, Any]) -> dict[str, Any]:
        document_id = str(payload.get("document_id") or "").strip()
        save_path = str(payload.get("save_path") or "").strip()
        if not document_id:
            raise HTTPException(status_code=422, detail="document_id is required")
        try:
            adapter = studio_adapter()
            before = adapter.studio_workspace_snapshot()
            entry = next(
                (item for item in before.get("documents", []) if item.get("document", {}).get("runtime_id") == document_id),
                None,
            )
            if entry is None:
                raise ValueError("Document is no longer open; refresh the workspace")
            document = entry["document"]
            if document.get("path"):
                saved = adapter.save_document(document_id=document_id, close_after_save=False, strict=True)
            elif save_path:
                saved = adapter.save_document_as(
                    save_path,
                    document_id=document_id,
                    close_after_save=False,
                    strict=True,
                )
            else:
                raise ValueError("save_path is required for an unsaved document")
            return {"ok": True, "saved": saved, "workspace": adapter.studio_workspace_snapshot()}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/workspace/save-as")
    def workspace_save_as(payload: dict[str, Any]) -> dict[str, Any]:
        document_id = str(payload.get("document_id") or "").strip()
        save_path = str(payload.get("save_path") or "").strip()
        if not document_id or not save_path:
            raise HTTPException(status_code=422, detail="document_id and save_path are required")
        try:
            adapter = studio_adapter()
            before = adapter.studio_workspace_snapshot()
            if not any(
                item.get("document", {}).get("runtime_id") == document_id
                for item in before.get("documents", [])
            ):
                raise ValueError("Document is no longer open; refresh the workspace")
            saved = adapter.save_document_as(
                save_path,
                document_id=document_id,
                close_after_save=False,
                strict=True,
            )
            return {"ok": True, "saved": saved, "workspace": adapter.studio_workspace_snapshot()}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/modules/{kind}/spec")
    def module_spec(kind: str) -> dict[str, Any]:
        try:
            return get_module(kind).spec()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/modules/{kind}/preview")
    def module_preview(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return preview_module(kind, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=_validation_detail(exc)) from exc
        except (CamshaftGeometryError, CamSynthesisError) as exc:
            raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc),
                "params": getattr(exc, "params", {})}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/modules/{kind}/cad/plan")
    def module_cad_plan(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return managed_pulley_plan(kind, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=_validation_detail(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/modules/{kind}/cad/create")
    def module_cad_create(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            module = get_module(kind)
            if not module.build:
                raise HTTPException(status_code=409, detail=f"{module.kind} has no CAD build yet")
            profile_payload = dict(payload.get("profile") or {})
            request = module.request_model.model_validate(profile_payload)
            if payload.get("confirm_write") is not True:
                raise HTTPException(status_code=409, detail="confirm_write=true is required")
            return create_module(studio_adapter(),module.kind,request.model_dump(exclude_none=True),
                                 str(payload.get("name") or ("Geomwright cam" if kind == "camshaft_lobe" else "Geomwright pulley")))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=_validation_detail(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            partial = getattr(exc,"partial_result",None)
            detail = {"message":str(exc),"partial_result":partial} if partial is not None else str(exc)
            raise HTTPException(status_code=502, detail=detail) from exc

    @app.post("/modules/{kind}/cad/jobs", status_code=202)
    def start_module_cad_job(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            module = get_module(kind)
            if not module.build:
                raise HTTPException(status_code=409, detail=f"{module.kind} has no CAD build yet")
            request = module.request_model.model_validate(dict(payload.get("profile") or {}))
            if payload.get("confirm_write") is not True:
                raise HTTPException(status_code=409, detail="confirm_write=true is required")
            if module.kind in {"chain_sprocket", "silent_chain_sprocket", "camshaft_lobe"}:
                managed_pulley_plan(module.kind, request.model_dump(exclude_none=True))
            return submit_cad_job(run_cad_job, (
                    module.kind,
                    request.model_dump(exclude_none=True),
                    str(payload.get("name") or ("Geomwright cam" if kind == "camshaft_lobe" else "Geomwright pulley")),
                ))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=_validation_detail(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/modules/{kind}/cad/update-jobs", status_code=202)
    def start_module_update_job(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            module = get_module(kind)
            if module.kind in {"camshaft_lobe", "silent_chain_sprocket", "chain_sprocket"}:
                raise HTTPException(status_code=409, detail="This module is create-only; build a new part instead")
            if not module.build:
                raise HTTPException(status_code=409, detail=f"{module.kind} has no CAD build yet")
            request = module.request_model.model_validate(dict(payload.get("profile") or {}))
            previous_request = module.request_model.model_validate(dict(payload.get("previous_profile") or {}))
            document_id = str(payload.get("document_id") or "").strip()
            block_id = str(payload.get("block_id") or "").strip()
            if not document_id or not block_id:
                raise HTTPException(status_code=422, detail="document_id and block_id are required")
            if payload.get("confirm_write") is not True:
                raise HTTPException(status_code=409, detail="confirm_write=true is required")
            return submit_cad_job(run_update_job, (
                    module.kind,
                    request.model_dump(exclude_none=True),
                    previous_request.model_dump(exclude_none=True),
                    str(payload.get("name") or "Geomwright pulley"),
                    document_id,
                    block_id,
                ))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=_validation_detail(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/cad/jobs/{job_id}")
    def module_cad_job(job_id: str) -> dict[str, Any]:
        try:
            return job_snapshot(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="CAD job was not found") from exc

    @app.post("/cad/jobs/{job_id}/cancel")
    def cancel_cad_job(job_id: str) -> dict[str, Any]:
        with cad_jobs_lock:
            job = cad_jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="CAD job was not found")
            if job["status"] not in {"completed", "failed", "cancelled"}:
                cad_cancel_events[job_id].set()
                job["stage"] = "cancelling"
            return dict(job)

    return app


app = create_app()
