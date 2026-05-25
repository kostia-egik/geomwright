from __future__ import annotations

import os
import re
import sqlite3
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


DEFAULT_KOMPAS_ENV_VARS = ("KOMPAS_ROOT", "KOMPAS_INSTALL_DIR", "KOMPAS_HOME")
DEFAULT_MODULE_DATABASE_SUFFIXES = (".db", ".sdb")
DEFAULT_RUNTIME_SUFFIXES = (".dll", ".rtw")
DEFAULT_INTERFACE_SCAN_SUFFIXES = (
    ".dll",
    ".rtw",
    ".chm",
    ".db",
    ".sdb",
    ".xml",
    ".ini",
    ".cfg",
    ".json",
    ".txt",
)
INTERFACE_HINT_PATTERNS: dict[str, tuple[str, ...]] = {
    "parameter_api": (
        "externalinterface",
        "external interface",
        "externalruncommand",
        "iexchange",
        "iparam",
        "parameter",
        "setparameter",
        "getparameter",
        "propertybag",
    ),
    "job_file": (
        ".ini",
        ".json",
        ".xml",
        ".cfg",
        "template",
        "profile",
        "schema",
        "import",
        "export",
    ),
    "calculation": (
        "calculate",
        "calculation",
        "verification",
        "design",
        "force",
        "material",
        "spring",
    ),
    "model_build": (
        "buildmodel",
        "build model",
        "createdocument",
        "createpart",
        "model",
        "drawing",
    ),
    "ui_workflow": (
        "dialog",
        "wizard",
        "propertypage",
        "modal",
        "messagebox",
        "window",
    ),
}
PROGRAMMATIC_ACCESS_TERMS = (
    "calculate",
    "calculation",
    "buildmodel",
    "build_model",
    "createpart",
    "createdocument",
    "setparameter",
    "getparameter",
    "externalinterface",
    "externalruncommand",
    "iexchange",
    "spring",
    "пруж",
)
SPRING_ENTRYPOINT_HINTS: dict[str, dict[str, Any]] = {
    "springccs": {
        "command_id": 101,
        "spring_kind": "compression_spring",
        "native_file_hint": "SPR_CCS.dll",
    },
    "springces": {
        "command_id": 102,
        "spring_kind": "extension_spring",
        "native_file_hint": "SPR_CES.dll",
    },
    "springcps": {
        "command_id": 103,
        "spring_kind": "disc_spring",
        "native_file_hint": "SPR_CPS.dll",
    },
    "springcon": {
        "command_id": 104,
        "spring_kind": "conical_spring",
        "native_file_hint": "SPR_CON.dll",
    },
    "springcrs": {
        "command_id": 105,
        "spring_kind": "torsion_spring",
        "native_file_hint": "SPR_CRS.dll",
    },
}


def list_native_modules(
    *,
    kompas_root: str | None = None,
    libs_dir: str | None = None,
    max_modules: int | None = 200,
) -> dict[str, Any]:
    """Return KOMPAS application-library manifests from a Libs directory."""
    resolved_libs_dir, checked_paths = _resolve_libs_dir(
        kompas_root=kompas_root,
        libs_dir=libs_dir,
    )
    if resolved_libs_dir is None:
        return {
            "ok": False,
            "libs_dir": None,
            "checked_paths": checked_paths,
            "module_count": 0,
            "modules": [],
            "error": "KOMPAS Libs directory was not found",
        }

    limit = _normalize_limit(max_modules, default=200, maximum=500)
    modules: list[dict[str, Any]] = []
    for module_dir in sorted((item for item in resolved_libs_dir.iterdir() if item.is_dir()), key=lambda p: p.name.lower()):
        if len(modules) >= limit:
            break
        manifest = _find_module_manifest(module_dir)
        if manifest is None:
            continue
        modules.append(_manifest_summary(module_dir, manifest))

    return {
        "ok": True,
        "libs_dir": str(resolved_libs_dir),
        "checked_paths": checked_paths,
        "module_count": len(modules),
        "truncated": _has_more_module_manifests(resolved_libs_dir, len(modules)),
        "modules": modules,
    }


def inspect_native_module(
    module: str = "Spring",
    *,
    kompas_root: str | None = None,
    libs_dir: str | None = None,
    include_database_inventory: bool = True,
    max_tables_per_database: int | None = 40,
) -> dict[str, Any]:
    """Inspect one installed KOMPAS application module without launching it."""
    modules_payload = list_native_modules(
        kompas_root=kompas_root,
        libs_dir=libs_dir,
        max_modules=500,
    )
    if not modules_payload.get("ok"):
        return {
            "ok": False,
            "module": module,
            "libs_dir": modules_payload.get("libs_dir"),
            "checked_paths": modules_payload.get("checked_paths", []),
            "error": modules_payload.get("error", "KOMPAS Libs directory was not found"),
        }

    resolved = _find_module_summary(modules_payload["modules"], module)
    if resolved is None:
        return {
            "ok": False,
            "module": module,
            "libs_dir": modules_payload["libs_dir"],
            "available_modules": [
                item["name"] for item in modules_payload["modules"]
            ][:100],
            "error": f"Native module '{module}' was not found",
        }

    module_dir = Path(resolved["path"])
    manifest = Path(resolved["manifest_path"])
    files = _module_files_summary(module_dir)
    databases = [
        item for item in files["files"] if item["suffix"].lower() in DEFAULT_MODULE_DATABASE_SUFFIXES
    ]
    runtime_files = [
        item for item in files["files"] if item["suffix"].lower() in DEFAULT_RUNTIME_SUFFIXES
    ]
    inventory: list[dict[str, Any]] = []
    if include_database_inventory:
        limit = _normalize_limit(max_tables_per_database, default=40, maximum=200)
        inventory = [
            _sqlite_inventory(Path(item["path"]), max_tables=limit)
            for item in databases
        ]

    payload = {
        "ok": True,
        "module": resolved["name"],
        "query": module,
        "title": resolved.get("title"),
        "app_id": resolved.get("app_id"),
        "path": str(module_dir),
        "manifest_path": str(manifest),
        "commands": _parse_manifest(manifest).get("commands", []),
        "files": files,
        "runtime_files": runtime_files,
        "databases": databases,
        "database_inventory": inventory,
        "integration_status": {
            "manifest_discovered": True,
            "runtime_files_discovered": bool(runtime_files),
            "database_inventory_available": bool(inventory),
            "launch_supported": False,
            "parameter_api_known": False,
            "mode": "read_only_discovery",
        },
    }
    if resolved["name"].lower() == "spring":
        payload["spring"] = _spring_module_summary(module_dir, payload["commands"])
    return payload


def inspect_native_module_interfaces(
    module: str = "Spring",
    *,
    kompas_root: str | None = None,
    libs_dir: str | None = None,
    max_files: int | None = 40,
    max_string_hits: int | None = 80,
    max_bytes_per_file: int | None = 1_000_000,
) -> dict[str, Any]:
    """Inspect static evidence for native-module parameter/session interfaces."""
    inspection = inspect_native_module(
        module,
        kompas_root=kompas_root,
        libs_dir=libs_dir,
        include_database_inventory=True,
    )
    if not inspection.get("ok"):
        return {
            "ok": False,
            "module": module,
            "stage": "inspect_native_module",
            "inspection": inspection,
            "error": inspection.get("error", "Native module was not found"),
        }

    module_dir = Path(inspection["path"])
    file_limit = _normalize_limit(max_files, default=40, maximum=200)
    hit_limit = _normalize_limit(max_string_hits, default=80, maximum=500)
    byte_limit = _normalize_limit(max_bytes_per_file, default=1_000_000, maximum=8_000_000)
    files = inspection.get("files", {}).get("files", [])
    scan_files = _interface_scan_files(files, limit=file_limit)
    string_hints = _scan_interface_string_hints(
        module_dir,
        scan_files,
        max_hits=hit_limit,
        max_bytes_per_file=byte_limit,
    )
    database_hints = _database_interface_hints(inspection.get("database_inventory", []))
    manifest_hints = _manifest_interface_hints(inspection)
    assessment = _native_interface_assessment(
        inspection,
        string_hints=string_hints,
        database_hints=database_hints,
        manifest_hints=manifest_hints,
    )
    return {
        "ok": True,
        "module": inspection["module"],
        "query": module,
        "title": inspection.get("title"),
        "app_id": inspection.get("app_id"),
        "path": inspection.get("path"),
        "manifest": manifest_hints,
        "artifact_summary": {
            "runtime_files": len(inspection.get("runtime_files", [])),
            "databases": len(inspection.get("databases", [])),
            "scanned_files": len(scan_files),
            "scan_file_limit": file_limit,
            "max_bytes_per_file": byte_limit,
        },
        "database_hints": database_hints,
        "string_hints": string_hints,
        "assessment": assessment,
        "spring": _spring_interface_summary(inspection) if inspection["module"].lower() == "spring" else None,
    }


def inspect_native_spring_workflow(
    *,
    kompas_root: str | None = None,
    libs_dir: str | None = None,
    max_tables: int | None = 80,
    max_sample_rows: int | None = 3,
) -> dict[str, Any]:
    """Build a bounded read-only dossier for the native Spring calculation workflow."""
    table_limit = _normalize_limit(max_tables, default=80, maximum=200)
    row_limit = _normalize_limit(max_sample_rows, default=3, maximum=10)
    inspection = inspect_native_module(
        "Spring",
        kompas_root=kompas_root,
        libs_dir=libs_dir,
        include_database_inventory=True,
        max_tables_per_database=table_limit,
    )
    if not inspection.get("ok"):
        return {
            "ok": False,
            "module": "Spring",
            "stage": "inspect_native_module",
            "inspection": inspection,
            "error": inspection.get("error", "Spring native module was not found"),
        }

    module_dir = Path(inspection["path"])
    workflow = _spring_calculation_workflow(inspection)
    reference_map = _spring_reference_database_map(
        inspection.get("database_inventory", []),
        max_sample_rows=row_limit,
    )
    return {
        "ok": True,
        "module": inspection["module"],
        "title": inspection.get("title"),
        "app_id": inspection.get("app_id"),
        "path": inspection.get("path"),
        "workflow_kind": "native_calculation_workflow",
        "commands": workflow["commands"],
        "workflow_capabilities": workflow["capabilities"],
        "reference_data": reference_map,
        "artifacts": {
            "manifest": inspection.get("manifest_path"),
            "runtime_files": [
                {
                    "name": item.get("name"),
                    "relative_path": item.get("relative_path"),
                    "size_bytes": item.get("size_bytes"),
                }
                for item in inspection.get("runtime_files", [])[:20]
            ],
            "databases": [
                {
                    "name": item.get("name"),
                    "relative_path": item.get("relative_path"),
                    "size_bytes": item.get("size_bytes"),
                }
                for item in inspection.get("databases", [])[:20]
            ],
            "help_database_detected": (module_dir / "SPRING_ru-RU.db").is_file(),
        },
        "automation_assessment": _spring_workflow_automation_assessment(reference_map),
        "next_experiments": [
            "Run start_native_module_result_probe(module='Spring', command_id=101, allow_interactive=true), complete one compression spring manually, then diff before/after captures.",
            "During the manual workflow, watch whether Spring creates or modifies a job/session file outside the reference databases.",
            "If a stable job/session artifact appears, inspect that artifact before attempting any parameter automation.",
        ],
    }


def probe_native_module_programmatic_access(
    module: str = "Spring",
    *,
    kompas_root: str | None = None,
    libs_dir: str | None = None,
    include_registry: bool = True,
    include_exports: bool = True,
    max_registry_keys: int | None = 25_000,
    max_registry_matches: int | None = 40,
    max_exports_per_file: int | None = 120,
) -> dict[str, Any]:
    """Probe stronger evidence for autonomous native-module automation access."""
    inspection = inspect_native_module(
        module,
        kompas_root=kompas_root,
        libs_dir=libs_dir,
        include_database_inventory=True,
    )
    if not inspection.get("ok"):
        return {
            "ok": False,
            "module": module,
            "stage": "inspect_native_module",
            "inspection": inspection,
            "error": inspection.get("error", "Native module was not found"),
        }

    module_dir = Path(inspection["path"])
    registry_key_limit = _normalize_limit(max_registry_keys, default=25_000, maximum=100_000)
    registry_match_limit = _normalize_limit(max_registry_matches, default=40, maximum=200)
    exports_limit = _normalize_limit(max_exports_per_file, default=120, maximum=500)
    search_terms = _programmatic_access_search_terms(inspection)
    runtime_files = inspection.get("runtime_files", [])
    export_inventory = (
        _runtime_export_inventory(module_dir, runtime_files, max_exports_per_file=exports_limit)
        if include_exports
        else {"enabled": False, "files": [], "summary": {}}
    )
    registry_hints = (
        _registry_programmatic_access_hints(
            inspection,
            search_terms=search_terms,
            max_keys=registry_key_limit,
            max_matches=registry_match_limit,
        )
        if include_registry
        else {"enabled": False, "roots": [], "summary": {}}
    )
    job_artifacts = _job_session_artifact_hints(inspection)
    string_evidence = _programmatic_string_evidence(inspection, search_terms=search_terms)
    assessment = _programmatic_access_assessment(
        inspection,
        exports=export_inventory,
        registry=registry_hints,
        job_artifacts=job_artifacts,
        string_evidence=string_evidence,
    )
    return {
        "ok": True,
        "module": inspection["module"],
        "query": module,
        "title": inspection.get("title"),
        "app_id": inspection.get("app_id"),
        "path": inspection.get("path"),
        "probe_kind": "programmatic_access",
        "evidence": {
            "registry": registry_hints,
            "exports": export_inventory,
            "job_session_artifacts": job_artifacts,
            "string_evidence": string_evidence,
            "manifest": _manifest_interface_hints(inspection),
        },
        "assessment": assessment,
    }


def inspect_native_module_entrypoints(
    module: str = "Spring",
    *,
    kompas_root: str | None = None,
    libs_dir: str | None = None,
    include_registry: bool = False,
    max_exports_per_file: int | None = 120,
) -> dict[str, Any]:
    """Return a static dossier for native DLL exports that look callable."""
    probe = probe_native_module_programmatic_access(
        module,
        kompas_root=kompas_root,
        libs_dir=libs_dir,
        include_registry=include_registry,
        include_exports=True,
        max_exports_per_file=max_exports_per_file,
    )
    if not probe.get("ok"):
        return {
            "ok": False,
            "module": module,
            "probe_kind": "native_entrypoints",
            "stage": "probe_native_module_programmatic_access",
            "programmatic_probe": probe,
            "error": probe.get("error", "Native module entrypoints could not be inspected"),
        }

    candidates = _entrypoint_candidates_from_probe(probe)
    assessment = _entrypoint_candidate_assessment(probe, candidates)
    return {
        "ok": True,
        "module": probe["module"],
        "query": module,
        "title": probe.get("title"),
        "app_id": probe.get("app_id"),
        "path": probe.get("path"),
        "probe_kind": "native_entrypoints",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "assessment": assessment,
        "programmatic_access_status": probe.get("assessment", {}).get("status"),
    }


def plan_native_entrypoint_validation(
    module: str = "Spring",
    *,
    export_name: str | None = None,
    command_id: int | str | None = None,
    kompas_root: str | None = None,
    libs_dir: str | None = None,
    max_exports_per_file: int | None = 120,
) -> dict[str, Any]:
    """Build a safe, non-executing validation plan for private native exports."""
    dossier = inspect_native_module_entrypoints(
        module,
        kompas_root=kompas_root,
        libs_dir=libs_dir,
        include_registry=False,
        max_exports_per_file=max_exports_per_file,
    )
    if not dossier.get("ok"):
        return {
            "ok": False,
            "module": module,
            "probe_kind": "native_entrypoint_validation_plan",
            "stage": "inspect_native_module_entrypoints",
            "entrypoint_dossier": dossier,
            "error": dossier.get("error", "Native entrypoint validation plan could not be built"),
        }

    selected = _select_entrypoint_validation_candidates(
        dossier.get("candidates", []),
        export_name=export_name,
        command_id=command_id,
    )
    assessment = _entrypoint_validation_assessment(dossier, selected)
    return {
        "ok": True,
        "module": dossier["module"],
        "query": module,
        "title": dossier.get("title"),
        "app_id": dossier.get("app_id"),
        "path": dossier.get("path"),
        "probe_kind": "native_entrypoint_validation_plan",
        "filters": {
            "export_name": export_name,
            "command_id": command_id,
        },
        "selected_count": len(selected),
        "selected_candidates": selected,
        "assessment": assessment,
        "harness": _entrypoint_validation_harness(selected),
        "source_entrypoint_status": dossier.get("assessment", {}).get("status"),
    }


def inspect_native_entrypoint_static_abi(
    module: str = "Spring",
    *,
    export_name: str | None = None,
    command_id: int | str | None = None,
    kompas_root: str | None = None,
    libs_dir: str | None = None,
    max_exports_per_file: int | None = 120,
    max_import_dlls: int | None = 80,
    max_imports_per_dll: int | None = 80,
) -> dict[str, Any]:
    """Inspect static PE ABI evidence for selected private native exports."""
    plan = plan_native_entrypoint_validation(
        module,
        export_name=export_name,
        command_id=command_id,
        kompas_root=kompas_root,
        libs_dir=libs_dir,
        max_exports_per_file=max_exports_per_file,
    )
    if not plan.get("ok"):
        return {
            "ok": False,
            "module": module,
            "probe_kind": "native_entrypoint_static_abi",
            "stage": "plan_native_entrypoint_validation",
            "validation_plan": plan,
            "error": plan.get("error", "Native entrypoint static ABI inventory could not be built"),
        }

    module_dir = Path(plan["path"])
    export_limit = _normalize_limit(max_exports_per_file, default=120, maximum=500)
    import_dll_limit = _normalize_limit(max_import_dlls, default=80, maximum=300)
    import_symbol_limit = _normalize_limit(max_imports_per_dll, default=80, maximum=500)
    entries = []
    for candidate in plan.get("selected_candidates", []):
        relative = str(candidate.get("relative_path") or candidate.get("file") or "")
        dll_path = module_dir / relative
        inventory = _pe_static_abi_inventory(
            dll_path,
            selected_export=str(candidate.get("export") or ""),
            max_exports=export_limit,
            max_import_dlls=import_dll_limit,
            max_imports_per_dll=import_symbol_limit,
        )
        entries.append(
            {
                "candidate": candidate,
                "dll_path": str(dll_path),
                "static_abi": inventory,
                "readiness": _static_abi_entry_readiness(candidate, inventory),
            }
        )

    return {
        "ok": True,
        "module": plan["module"],
        "query": module,
        "title": plan.get("title"),
        "app_id": plan.get("app_id"),
        "path": plan.get("path"),
        "probe_kind": "native_entrypoint_static_abi",
        "filters": plan.get("filters", {}),
        "entry_count": len(entries),
        "entries": entries,
        "assessment": _static_abi_inventory_assessment(entries, plan),
        "execution_policy": {
            "loads_library": False,
            "calls_exports": False,
            "safe_for_production_bridge": True,
            "promotion_to_loader_probe_allowed": False,
        },
    }


def preview_native_module_launch(
    module: str = "Spring",
    *,
    command_id: int | str | None = 101,
    command_title: str | None = None,
    kompas_root: str | None = None,
    libs_dir: str | None = None,
) -> dict[str, Any]:
    """Resolve a native KOMPAS module command before interactive launch."""
    inspection = inspect_native_module(
        module,
        kompas_root=kompas_root,
        libs_dir=libs_dir,
        include_database_inventory=False,
    )
    if not inspection.get("ok"):
        return {
            "ok": False,
            "module": module,
            "command_id": command_id,
            "command_title": command_title,
            "stage": "inspect_native_module",
            "error": inspection.get("error", "Native module was not found"),
            "inspection": inspection,
        }

    command = _find_command(inspection.get("commands", []), command_id, command_title)
    if command is None:
        return {
            "ok": False,
            "module": inspection["module"],
            "command_id": command_id,
            "command_title": command_title,
            "stage": "resolve_command",
            "available_commands": inspection.get("commands", []),
            "error": "Native module command was not found",
        }

    return {
        "ok": True,
        "module": inspection["module"],
        "title": inspection.get("title"),
        "app_id": inspection.get("app_id"),
        "path": inspection.get("path"),
        "manifest_path": inspection.get("manifest_path"),
        "command": command,
        "launch_contract": {
            "mode": "interactive_native_module_command",
            "parameter_automation": False,
            "requires_registered_library": True,
            "safety": "preview_only unless allow_interactive is true",
        },
    }


def _resolve_libs_dir(
    *,
    kompas_root: str | None,
    libs_dir: str | None,
) -> tuple[Path | None, list[str]]:
    checked_paths: list[str] = []
    if libs_dir:
        candidate = Path(libs_dir).expanduser()
        checked_paths.append(str(candidate))
        if candidate.is_dir():
            return candidate, checked_paths
        return None, checked_paths

    for root in _candidate_kompas_roots(kompas_root):
        candidate = root / "Libs"
        checked_paths.append(str(candidate))
        if candidate.is_dir():
            return candidate, checked_paths
    return None, checked_paths


def _candidate_kompas_roots(explicit_root: str | None) -> list[Path]:
    roots: list[Path] = []
    if explicit_root:
        roots.append(Path(explicit_root).expanduser())
    for env_name in DEFAULT_KOMPAS_ENV_VARS:
        value = os.environ.get(env_name)
        if value:
            roots.append(Path(value).expanduser())

    program_files = [os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432")]
    for base in program_files:
        if not base:
            continue
        ascon_dir = Path(base) / "ASCON"
        if not ascon_dir.is_dir():
            continue
        roots.extend(sorted(ascon_dir.glob("KOMPAS-3D v*"), reverse=True))

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _find_module_manifest(module_dir: Path) -> Path | None:
    preferred = module_dir / f"{module_dir.name.upper()}.xml"
    if preferred.is_file():
        return preferred
    manifests = sorted(module_dir.glob("*.xml"))
    return manifests[0] if manifests else None


def _manifest_summary(module_dir: Path, manifest: Path) -> dict[str, Any]:
    parsed = _parse_manifest(manifest)
    commands = parsed.get("commands", [])
    return {
        "name": module_dir.name,
        "title": parsed.get("title"),
        "app_id": parsed.get("app_id"),
        "path": str(module_dir),
        "manifest_path": str(manifest),
        "command_count": len(commands),
        "commands": commands,
    }


def _parse_manifest(manifest: Path) -> dict[str, Any]:
    try:
        tree = ET.parse(manifest)
    except (ET.ParseError, OSError, UnicodeError) as exc:
        return {
            "ok": False,
            "manifest_path": str(manifest),
            "error": str(exc),
            "commands": [],
        }

    root = tree.getroot()
    commands: list[dict[str, Any]] = []
    for element in root.iter():
        if _local_name(element.tag) != "appCommand":
            continue
        command_id = element.attrib.get("id")
        commands.append(
            {
                "id": int(command_id) if command_id and command_id.isdigit() else command_id,
                "title": element.attrib.get("title"),
                "icon": element.attrib.get("appIcon"),
            }
        )
    return {
        "ok": True,
        "manifest_path": str(manifest),
        "app_id": root.attrib.get("id"),
        "title": root.attrib.get("title"),
        "help_db": root.attrib.get("helpDb"),
        "show_in_menu": _parse_bool(root.attrib.get("showInMenu")),
        "commands": commands,
    }


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    return None


def _find_module_summary(modules: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    needle = query.strip().lower()
    if not needle:
        return None
    for item in modules:
        candidates = [
            item.get("name"),
            item.get("title"),
            item.get("app_id"),
        ]
        if any(str(candidate).lower() == needle for candidate in candidates if candidate):
            return item
    for item in modules:
        candidates = [item.get("name"), item.get("title")]
        if any(needle in str(candidate).lower() for candidate in candidates if candidate):
            return item
    return None


def _find_command(
    commands: list[dict[str, Any]],
    command_id: int | str | None,
    command_title: str | None,
) -> dict[str, Any] | None:
    normalized_title = str(command_title or "").strip().lower()
    normalized_id = str(command_id).strip() if command_id not in (None, "") else ""
    if normalized_id:
        for command in commands:
            if str(command.get("id")).strip() == normalized_id:
                return command
    if normalized_title:
        for command in commands:
            title = str(command.get("title") or "").strip().lower()
            if title == normalized_title or normalized_title in title:
                return command
    return None


def _module_files_summary(module_dir: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted((item for item in module_dir.rglob("*") if item.is_file()), key=lambda p: str(p).lower()):
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        files.append(
            {
                "name": path.name,
                "relative_path": str(path.relative_to(module_dir)),
                "path": str(path),
                "suffix": path.suffix,
                "size_bytes": size,
            }
        )
    return {
        "file_count": len(files),
        "files": files[:200],
        "truncated": len(files) > 200,
    }


def _sqlite_inventory(path: Path, *, max_tables: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": str(path),
        "name": path.name,
        "ok": False,
        "tables": [],
    }
    connection = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = connection.execute(
            """
            select name, type
            from sqlite_master
            where type in ('table', 'view')
            order by name
            """
        ).fetchall()
        tables = []
        for name, table_type in rows[:max_tables]:
            quoted = _quote_sqlite_identifier(name)
            count = None
            if table_type == "table":
                count = connection.execute(f"select count(*) from {quoted}").fetchone()[0]
            columns = connection.execute(f"pragma table_info({quoted})").fetchall()
            tables.append(
                {
                    "name": name,
                    "type": table_type,
                    "row_count": count,
                    "columns": [column[1] for column in columns],
                }
            )
        payload.update(
            {
                "ok": True,
                "table_count": len(rows),
                "tables": tables,
                "truncated": len(rows) > max_tables,
            }
        )
    except sqlite3.Error as exc:
        payload["error"] = str(exc)
    finally:
        if connection is not None:
            connection.close()
    return payload


def _interface_scan_files(files: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for item in files:
        suffix = str(item.get("suffix") or "").lower()
        if suffix not in DEFAULT_INTERFACE_SCAN_SUFFIXES:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def _scan_interface_string_hints(
    module_dir: Path,
    files: list[dict[str, Any]],
    *,
    max_hits: int,
    max_bytes_per_file: int,
) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    scanned: list[dict[str, Any]] = []
    for item in files:
        path = Path(str(item.get("path", "")))
        if not _is_relative_to(path, module_dir):
            continue
        suffix = str(item.get("suffix") or "").lower()
        try:
            data = path.read_bytes()[:max_bytes_per_file]
            size = path.stat().st_size
        except OSError as exc:
            scanned.append(
                {
                    "relative_path": item.get("relative_path"),
                    "suffix": suffix,
                    "ok": False,
                    "error": str(exc),
                }
            )
            continue
        scanned.append(
            {
                "relative_path": item.get("relative_path"),
                "suffix": suffix,
                "ok": True,
                "size_bytes": size,
                "bytes_scanned": min(size, max_bytes_per_file),
                "truncated": size > max_bytes_per_file,
            }
        )
        for text in _extract_bounded_strings(data):
            categories = _hint_categories(text)
            if not categories:
                continue
            hits.append(
                {
                    "relative_path": item.get("relative_path"),
                    "suffix": suffix,
                    "categories": categories,
                    "text": _compact_hint_text(text),
                }
            )
            if len(hits) >= max_hits:
                break
        if len(hits) >= max_hits:
            break
    category_counts: dict[str, int] = {category: 0 for category in INTERFACE_HINT_PATTERNS}
    for hit in hits:
        for category in hit["categories"]:
            category_counts[category] = category_counts.get(category, 0) + 1
    return {
        "scanned": scanned,
        "hit_count": len(hits),
        "truncated": len(hits) >= max_hits,
        "category_counts": category_counts,
        "hits": hits,
    }


def _extract_bounded_strings(data: bytes) -> list[str]:
    strings: list[str] = []
    seen: set[str] = set()
    for raw in re.findall(rb"[\x20-\x7e]{4,}", data):
        text = raw.decode("ascii", errors="ignore").strip()
        if text and text not in seen:
            strings.append(text)
            seen.add(text)
    try:
        decoded = data.decode("utf-16le", errors="ignore")
    except UnicodeError:
        decoded = ""
    for text in re.findall(r"[ -~]{4,}", decoded):
        text = text.strip()
        if text and text not in seen:
            strings.append(text)
            seen.add(text)
    return strings[:2000]


def _hint_categories(text: str) -> list[str]:
    lowered = text.lower()
    categories = []
    for category, patterns in INTERFACE_HINT_PATTERNS.items():
        if any(pattern in lowered for pattern in patterns):
            categories.append(category)
    return categories


def _compact_hint_text(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= 160:
        return text
    return f"{text[:157]}..."


def _database_interface_hints(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    databases: list[dict[str, Any]] = []
    candidate_terms = (
        "param",
        "material",
        "spring",
        "calc",
        "result",
        "force",
        "diagram",
        "table",
    )
    for database in inventory:
        tables = []
        for table in database.get("tables", []):
            haystack = " ".join(
                [str(table.get("name") or "")]
                + [str(column) for column in table.get("columns", [])]
            ).lower()
            matched_terms = [term for term in candidate_terms if term in haystack]
            if matched_terms:
                tables.append(
                    {
                        "name": table.get("name"),
                        "type": table.get("type"),
                        "row_count": table.get("row_count"),
                        "matched_terms": matched_terms,
                        "columns": table.get("columns", [])[:20],
                    }
                )
        databases.append(
            {
                "name": database.get("name"),
                "ok": database.get("ok"),
                "table_count": database.get("table_count"),
                "candidate_table_count": len(tables),
                "candidate_tables": tables[:20],
                "truncated": len(tables) > 20 or bool(database.get("truncated")),
            }
        )
    return {
        "database_count": len(databases),
        "databases": databases,
        "notes": [
            "SQLite/SDB tables are treated as calculation/reference data, not as a supported automation API.",
        ],
    }


def _manifest_interface_hints(inspection: dict[str, Any]) -> dict[str, Any]:
    commands = inspection.get("commands", [])
    return {
        "manifest_path": inspection.get("manifest_path"),
        "app_id": inspection.get("app_id"),
        "title": inspection.get("title"),
        "command_count": len(commands),
        "commands": commands[:50],
        "parameter_schema_detected": False,
        "notes": [
            "The native module manifest exposes commands, not a parameter/session schema.",
        ],
    }


def _native_interface_assessment(
    inspection: dict[str, Any],
    *,
    string_hints: dict[str, Any],
    database_hints: dict[str, Any],
    manifest_hints: dict[str, Any],
) -> dict[str, Any]:
    category_counts = string_hints.get("category_counts", {})
    parameter_hits = int(category_counts.get("parameter_api", 0))
    job_hits = int(category_counts.get("job_file", 0))
    model_hits = int(category_counts.get("model_build", 0))
    manifest_schema = bool(manifest_hints.get("parameter_schema_detected"))
    public_contract_detected = manifest_schema or (parameter_hits >= 3 and (job_hits > 0 or model_hits > 0))
    status = (
        "public_parameter_contract_detected"
        if public_contract_detected
        else "interface_hints_detected_requires_manual_validation"
        if parameter_hits > 0 or job_hits > 0
        else "no_public_parameter_contract_detected"
    )
    return {
        "status": status,
        "public_parameter_contract_detected": public_contract_detected,
        "parameter_api_hint_count": parameter_hits,
        "job_file_hint_count": job_hits,
        "model_build_hint_count": model_hits,
        "job_file_hints_detected": job_hits > 0,
        "database_reference_detected": any(
            database.get("candidate_table_count", 0) > 0
            for database in database_hints.get("databases", [])
        ),
        "confidence": "heuristic_static_scan",
        "limits": [
            "This is a static artifact scan; it cannot prove absence of a private COM interface.",
            "DLL strings and database table names are hints only.",
        ],
        "next_experiments": _native_interface_next_experiments(inspection["module"], status),
    }


def _native_interface_next_experiments(module: str, status: str) -> list[str]:
    generic = [
        "Run start_native_module_result_probe with allow_interactive=true, finish the native UI manually, then diff before/after captures.",
        "Look for files created or modified by the native workflow during manual completion.",
    ]
    if module.lower() == "spring":
        generic.insert(
            0,
            "For Spring/101, complete one compression-spring workflow to 3D model creation and inspect the resulting model tree.",
        )
    if status == "public_parameter_contract_detected":
        generic.append("Inspect the specific hinted artifacts before attempting parameter automation.")
    elif status == "interface_hints_detected_requires_manual_validation":
        generic.append("Validate whether hinted artifacts are real input contracts or just internal resources.")
    else:
        generic.append("Treat the module as interactive until a documented external/session contract is found.")
    return generic


def _programmatic_access_search_terms(inspection: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for value in (
        inspection.get("module"),
        inspection.get("title"),
        inspection.get("app_id"),
    ):
        if value:
            terms.extend(re.findall(r"[\wА-Яа-я]+", str(value).lower()))
    for item in inspection.get("runtime_files", []):
        name = str(item.get("name") or "").lower()
        stem = Path(name).stem
        if stem:
            terms.append(stem)
        terms.append(name)
    terms.extend(PROGRAMMATIC_ACCESS_TERMS)
    compact: list[str] = []
    seen: set[str] = set()
    for term in terms:
        term = term.strip().lower()
        if len(term) < 3 or term in seen or not re.search(r"[a-zа-я]", term):
            continue
        compact.append(term)
        seen.add(term)
    return compact[:80]


def _runtime_export_inventory(
    module_dir: Path,
    runtime_files: list[dict[str, Any]],
    *,
    max_exports_per_file: int,
) -> dict[str, Any]:
    files = []
    summary = {
        "file_count": 0,
        "pe_file_count": 0,
        "exporting_file_count": 0,
        "automation_export_count": 0,
    }
    for item in runtime_files[:50]:
        path = Path(str(item.get("path", "")))
        if not _is_relative_to(path, module_dir):
            continue
        export_info = _pe_export_names(path, max_exports=max_exports_per_file)
        automation_exports = [
            name
            for name in export_info.get("exports", [])
            if _looks_like_programmatic_symbol(name)
        ]
        files.append(
            {
                "relative_path": item.get("relative_path"),
                "name": item.get("name"),
                "suffix": item.get("suffix"),
                "ok": export_info.get("ok"),
                "is_pe": export_info.get("is_pe", False),
                "machine": export_info.get("machine"),
                "architecture": export_info.get("architecture"),
                "export_count": export_info.get("export_count", 0),
                "exports_returned": len(export_info.get("exports", [])),
                "exports_truncated": export_info.get("truncated", False),
                "automation_exports": automation_exports[:20],
                "error": export_info.get("error"),
            }
        )
        summary["file_count"] += 1
        if export_info.get("is_pe"):
            summary["pe_file_count"] += 1
        if int(export_info.get("export_count") or 0) > 0:
            summary["exporting_file_count"] += 1
        summary["automation_export_count"] += len(automation_exports)
    return {
        "enabled": True,
        "summary": summary,
        "files": files,
        "notes": [
            "PE exports are strong evidence only when they expose domain-level automation functions, not generic DLL registration entrypoints.",
        ],
    }


def _pe_export_names(path: Path, *, max_exports: int) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "is_pe": False, "exports": [], "export_count": 0}
    try:
        data = path.read_bytes()
    except OSError as exc:
        payload["error"] = str(exc)
        return payload
    if len(data) < 0x40 or data[:2] != b"MZ":
        payload["error"] = "not a PE/MZ file"
        return payload
    try:
        pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe_offset : pe_offset + 4] != b"PE\0\0":
            payload["error"] = "PE signature not found"
            return payload
        coff = pe_offset + 4
        machine = struct.unpack_from("<H", data, coff)[0]
        payload["machine"] = f"0x{machine:04X}"
        payload["architecture"] = _pe_machine_architecture(machine)
        section_count = struct.unpack_from("<H", data, coff + 2)[0]
        optional_size = struct.unpack_from("<H", data, coff + 16)[0]
        optional = coff + 20
        magic = struct.unpack_from("<H", data, optional)[0]
        data_directory = optional + (96 if magic == 0x10B else 112 if magic == 0x20B else -1)
        if data_directory < optional:
            payload["error"] = "unknown PE optional header magic"
            return payload
        export_rva, _export_size = struct.unpack_from("<II", data, data_directory)
        payload["is_pe"] = True
        if export_rva == 0:
            payload.update({"ok": True, "exports": [], "export_count": 0, "truncated": False})
            return payload
        sections = []
        section_offset = optional + optional_size
        for index in range(section_count):
            offset = section_offset + index * 40
            virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", data, offset + 8)
            sections.append((virtual_address, max(virtual_size, raw_size), raw_pointer, raw_size))
        export_offset = _pe_rva_to_offset(export_rva, sections)
        if export_offset is None:
            payload["error"] = "export directory RVA could not be mapped"
            return payload
        name_count = struct.unpack_from("<I", data, export_offset + 24)[0]
        names_rva = struct.unpack_from("<I", data, export_offset + 32)[0]
        names_offset = _pe_rva_to_offset(names_rva, sections)
        if names_offset is None:
            payload["error"] = "export names RVA could not be mapped"
            return payload
        names = []
        for index in range(min(name_count, max_exports)):
            name_rva = struct.unpack_from("<I", data, names_offset + index * 4)[0]
            name_offset = _pe_rva_to_offset(name_rva, sections)
            if name_offset is None:
                continue
            names.append(_read_c_string(data, name_offset))
        payload.update(
            {
                "ok": True,
                "exports": names,
                "export_count": name_count,
                "truncated": name_count > max_exports,
            }
        )
    except (IndexError, struct.error, ValueError) as exc:
        payload["error"] = f"PE export parse failed: {exc}"
    return payload


def _pe_rva_to_offset(rva: int, sections: list[tuple[int, int, int, int]]) -> int | None:
    for virtual_address, virtual_size, raw_pointer, raw_size in sections:
        if virtual_address <= rva < virtual_address + virtual_size:
            offset = raw_pointer + (rva - virtual_address)
            if offset < raw_pointer + raw_size:
                return offset
    return None


def _pe_machine_architecture(machine: int) -> str:
    return {
        0x014C: "x86",
        0x8664: "x64",
        0x01C0: "arm",
        0x01C4: "armv7",
        0xAA64: "arm64",
    }.get(machine, "unknown")


def _read_c_string(data: bytes, offset: int) -> str:
    end = data.find(b"\0", offset)
    if end < 0:
        end = min(len(data), offset + 256)
    return data[offset:end].decode("ascii", errors="replace")


def _looks_like_programmatic_symbol(name: str) -> bool:
    lowered = name.lower()
    if lowered in {"dllcanunloadnow", "dllgetclassobject", "dllregisterserver", "dllunregisterserver"}:
        return False
    return any(term in lowered for term in PROGRAMMATIC_ACCESS_TERMS)


def _registry_programmatic_access_hints(
    inspection: dict[str, Any],
    *,
    search_terms: list[str],
    max_keys: int,
    max_matches: int,
) -> dict[str, Any]:
    if os.name != "nt":
        return {
            "enabled": True,
            "available": False,
            "roots": [],
            "summary": {"match_count": 0},
            "error": "Windows registry is unavailable on this platform",
        }
    try:
        import winreg
    except ImportError as exc:
        return {
            "enabled": True,
            "available": False,
            "roots": [],
            "summary": {"match_count": 0},
            "error": str(exc),
        }

    module_dir = str(Path(inspection["path"]).resolve()).lower()
    runtime_names = {
        str(item.get("name") or "").lower()
        for item in inspection.get("runtime_files", [])
        if item.get("name")
    }
    roots = [
        _scan_registry_tree(
            winreg.HKEY_CLASSES_ROOT,
            "CLSID",
            search_terms=search_terms,
            module_dir=module_dir,
            runtime_names=runtime_names,
            max_depth=2,
            max_keys=max_keys,
            max_matches=max_matches,
        ),
        _scan_registry_tree(
            winreg.HKEY_CLASSES_ROOT,
            "TypeLib",
            search_terms=search_terms,
            module_dir=module_dir,
            runtime_names=runtime_names,
            max_depth=3,
            max_keys=max_keys,
            max_matches=max_matches,
        ),
    ]
    matches = [match for root in roots for match in root.get("matches", [])]
    direct_module_servers = [
        match
        for match in matches
        if match.get("module_path_match") and "inprocserver32" in str(match.get("key", "")).lower()
    ]
    typelib_matches = [
        match
        for match in matches
        if "typelib" in str(match.get("key", "")).lower()
    ]
    return {
        "enabled": True,
        "available": True,
        "summary": {
            "keys_scanned": sum(int(root.get("keys_scanned") or 0) for root in roots),
            "truncated": any(root.get("truncated") for root in roots),
            "match_count": len(matches),
            "direct_module_com_server_count": len(direct_module_servers),
            "typelib_match_count": len(typelib_matches),
        },
        "roots": roots,
        "notes": [
            "Registry matches prove registration only when they point at the module runtime path or expose a module-specific TypeLib/ProgID.",
        ],
    }


def _scan_registry_tree(
    root: Any,
    subkey: str,
    *,
    search_terms: list[str],
    module_dir: str,
    runtime_names: set[str],
    max_depth: int,
    max_keys: int,
    max_matches: int,
) -> dict[str, Any]:
    import winreg

    matches: list[dict[str, Any]] = []
    scanned = 0
    truncated = False

    def visit(key_path: str, depth: int) -> None:
        nonlocal scanned, truncated
        if scanned >= max_keys or len(matches) >= max_matches:
            truncated = True
            return
        try:
            with winreg.OpenKey(root, key_path) as key:
                scanned += 1
                values = _registry_key_values(winreg, key)
                match = _registry_values_match(
                    key_path,
                    values,
                    search_terms=search_terms,
                    module_dir=module_dir,
                    runtime_names=runtime_names,
                )
                if match is not None:
                    matches.append(match)
                    if len(matches) >= max_matches:
                        truncated = True
                        return
                if depth >= max_depth:
                    return
                index = 0
                while True:
                    if scanned >= max_keys or len(matches) >= max_matches:
                        truncated = True
                        return
                    try:
                        child = winreg.EnumKey(key, index)
                    except OSError:
                        break
                    visit(f"{key_path}\\{child}", depth + 1)
                    index += 1
        except OSError:
            return

    visit(subkey, 0)
    return {
        "root": f"HKCR\\{subkey}",
        "keys_scanned": scanned,
        "truncated": truncated,
        "matches": matches,
    }


def _registry_key_values(winreg: Any, key: Any) -> list[dict[str, Any]]:
    values = []
    index = 0
    while index < 12:
        try:
            name, value, _value_type = winreg.EnumValue(key, index)
        except OSError:
            break
        if isinstance(value, (str, int, float)):
            values.append({"name": name or "(default)", "value": str(value)})
        index += 1
    try:
        default, _value_type = winreg.QueryValueEx(key, "")
        if isinstance(default, (str, int, float)) and not any(item["name"] == "(default)" for item in values):
            values.insert(0, {"name": "(default)", "value": str(default)})
    except OSError:
        pass
    return values


def _registry_values_match(
    key_path: str,
    values: list[dict[str, Any]],
    *,
    search_terms: list[str],
    module_dir: str,
    runtime_names: set[str],
) -> dict[str, Any] | None:
    haystack = " ".join([key_path] + [item["value"] for item in values]).lower()
    matched_terms = [term for term in search_terms if term in haystack][:12]
    runtime_matches = [name for name in runtime_names if name and name in haystack][:12]
    module_path_match = module_dir in haystack.replace("/", "\\")
    if not matched_terms and not runtime_matches and not module_path_match:
        return None
    return {
        "key": f"HKCR\\{key_path}",
        "matched_terms": matched_terms,
        "runtime_name_matches": runtime_matches,
        "module_path_match": module_path_match,
        "values": values[:6],
    }


def _job_session_artifact_hints(inspection: dict[str, Any]) -> dict[str, Any]:
    artifacts = []
    weak_suffixes = {".ini", ".cfg", ".json"}
    xml_manifest = str(inspection.get("manifest_path") or "")
    for item in inspection.get("files", {}).get("files", []):
        suffix = str(item.get("suffix") or "").lower()
        path = str(item.get("path") or "")
        if suffix == ".xml" and path == xml_manifest:
            continue
        if suffix not in weak_suffixes and suffix != ".xml":
            continue
        lowered = " ".join(
            [
                str(item.get("name") or ""),
                str(item.get("relative_path") or ""),
            ]
        ).lower()
        categories = [
            category
            for category, terms in {
                "profile": ("profile", "template", "default"),
                "import_export": ("import", "export", "report"),
                "parameter": ("param", "parameter", "spring"),
                "session": ("session", "state", "job", "task"),
            }.items()
            if any(term in lowered for term in terms)
        ]
        artifacts.append(
            {
                "name": item.get("name"),
                "relative_path": item.get("relative_path"),
                "suffix": suffix,
                "size_bytes": item.get("size_bytes"),
                "categories": categories,
            }
        )
    return {
        "artifact_count": len(artifacts),
        "artifacts": artifacts[:30],
        "truncated": len(artifacts) > 30,
        "contract_detected": False,
        "notes": [
            "Config/profile artifacts are not treated as an input contract unless a schema or documented loader is found.",
        ],
    }


def _programmatic_string_evidence(inspection: dict[str, Any], *, search_terms: list[str]) -> dict[str, Any]:
    module_dir = Path(inspection["path"])
    files = _interface_scan_files(inspection.get("files", {}).get("files", []), limit=30)
    hints = _scan_interface_string_hints(module_dir, files, max_hits=80, max_bytes_per_file=1_000_000)
    strong_hits = []
    for hit in hints.get("hits", []):
        text = str(hit.get("text") or "")
        if any(term in text.lower() for term in PROGRAMMATIC_ACCESS_TERMS):
            strong_hits.append(hit)
    return {
        "hit_count": hints.get("hit_count", 0),
        "category_counts": hints.get("category_counts", {}),
        "strong_programmatic_hit_count": len(strong_hits),
        "strong_programmatic_hits": strong_hits[:20],
        "notes": [
            "Strings can suggest private internals, but do not prove a stable callable API.",
        ],
    }


def _programmatic_access_assessment(
    inspection: dict[str, Any],
    *,
    exports: dict[str, Any],
    registry: dict[str, Any],
    job_artifacts: dict[str, Any],
    string_evidence: dict[str, Any],
) -> dict[str, Any]:
    registry_summary = registry.get("summary", {})
    export_summary = exports.get("summary", {})
    direct_com_servers = int(registry_summary.get("direct_module_com_server_count") or 0)
    typelib_matches = int(registry_summary.get("typelib_match_count") or 0)
    automation_exports = int(export_summary.get("automation_export_count") or 0)
    strong_strings = int(string_evidence.get("strong_programmatic_hit_count") or 0)
    entrypoint_candidate_detected = direct_com_servers > 0 or typelib_matches > 0 or automation_exports > 0
    public_callable_contract_detected = direct_com_servers > 0 and typelib_matches > 0
    full_access_supported = False
    if entrypoint_candidate_detected:
        status = "programmatic_entrypoint_candidate_requires_validation"
    elif strong_strings > 0 or job_artifacts.get("artifact_count", 0) > 0:
        status = "weak_internal_hints_no_callable_contract"
    else:
        status = "no_public_programmatic_access_detected"
    return {
        "status": status,
        "full_autonomous_access_supported": full_access_supported,
        "public_callable_contract_detected": public_callable_contract_detected,
        "programmatic_entrypoint_candidate_detected": entrypoint_candidate_detected,
        "direct_module_com_server_detected": direct_com_servers > 0,
        "typelib_detected": typelib_matches > 0,
        "domain_exports_detected": automation_exports > 0,
        "job_session_contract_detected": bool(job_artifacts.get("contract_detected")),
        "confidence": "stronger_static_probe",
        "verdict": (
            "No supported autonomous parameter/calculation/build contract is proven. "
            "Treat this module as unsuitable for autonomous MCP work until a callable COM/TypeLib/export/job contract is validated."
        ),
        "limits": [
            "Registry and PE export probing can miss private in-process interfaces that are created only after loading the module.",
            "Weak strings and config files are not sufficient for autonomous integration.",
        ],
        "next_experiments": [
            "If a candidate COM/TypeLib/export appears, call only a harmless introspection method first and document the exact contract.",
            "If no candidate appears for Spring, stop investing in UI-driven integration and design an autonomous spring calculation/modeling path.",
            "Keep launch/readback tools as diagnostics and fallback, not as the production autonomous workflow.",
        ],
    }


def _entrypoint_candidates_from_probe(probe: dict[str, Any]) -> list[dict[str, Any]]:
    commands_by_id = {
        int(command["id"]): command
        for command in probe.get("evidence", {}).get("manifest", {}).get("commands", [])
        if command.get("id") is not None
    }
    candidates: list[dict[str, Any]] = []
    for file_info in probe.get("evidence", {}).get("exports", {}).get("files", []):
        exports = list(file_info.get("automation_exports") or [])
        if not exports:
            continue
        for export_name in exports:
            metadata = _entrypoint_candidate_metadata(
                export_name,
                relative_path=str(file_info.get("relative_path") or file_info.get("name") or ""),
            )
            command_id = metadata.get("command_id")
            command = commands_by_id.get(command_id) if isinstance(command_id, int) else None
            candidates.append(
                {
                    "export": export_name,
                    "relative_path": file_info.get("relative_path"),
                    "file": file_info.get("name"),
                    "machine": file_info.get("machine"),
                    "architecture": file_info.get("architecture"),
                    "spring_kind": metadata.get("spring_kind"),
                    "command_id": command_id,
                    "command_title": command.get("title") if command else None,
                    "confidence": metadata["confidence"],
                    "evidence": metadata["evidence"],
                    "callability": "unknown_signature",
                    "production_safe": False,
                    "risk": "native_private_entrypoint_without_signature",
                }
            )
    return candidates


def _entrypoint_candidate_metadata(export_name: str, *, relative_path: str) -> dict[str, Any]:
    lowered_export = export_name.lower()
    lowered_path = relative_path.lower()
    hint = SPRING_ENTRYPOINT_HINTS.get(lowered_export)
    evidence = []
    if hint:
        evidence.append("known_spring_export_name")
        native_file_hint = str(hint["native_file_hint"]).lower()
        if native_file_hint in lowered_path:
            evidence.append("export_file_matches_spring_kind")
        return {
            "command_id": hint["command_id"],
            "spring_kind": hint["spring_kind"],
            "confidence": "medium_static_name_match",
            "evidence": evidence,
        }
    for name, candidate in SPRING_ENTRYPOINT_HINTS.items():
        if name in lowered_export or str(candidate["native_file_hint"]).lower() in lowered_path:
            evidence.append("partial_spring_name_or_file_match")
            return {
                "command_id": candidate["command_id"],
                "spring_kind": candidate["spring_kind"],
                "confidence": "low_static_name_match",
                "evidence": evidence,
            }
    return {
        "command_id": None,
        "spring_kind": None,
        "confidence": "unclassified_export",
        "evidence": ["programmatic_symbol_name"],
    }


def _entrypoint_candidate_assessment(probe: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    mapped_candidates = [candidate for candidate in candidates if candidate.get("command_id") is not None]
    return {
        "status": (
            "private_entrypoint_candidates_mapped"
            if mapped_candidates
            else "no_domain_entrypoint_candidates_mapped"
        ),
        "public_callable_contract_detected": False,
        "full_autonomous_access_supported": False,
        "reverse_engineering_candidate_count": len(candidates),
        "mapped_to_native_command_count": len(mapped_candidates),
        "validation_stage": "static_export_dossier",
        "verdict": (
            "Domain exports can guide reverse engineering, but they are not a supported Spring API without signatures, "
            "input structs, ownership rules, threading model, and success/error contracts."
        ),
        "safe_validation_plan": [
            "Do not call unknown exports inside the production bridge process.",
            "If validation is approved, use an isolated throwaway process with crash containment and no open user documents.",
            "First inspect signatures with dedicated native tooling before any call attempt.",
            "Only promote an entrypoint after a repeatable no-op/introspection call and a documented input/output contract.",
        ],
        "fallback_decision": (
            "Until an export contract is validated, production autonomous spring work should use an owned calculation/modeling path; "
            "native Spring remains diagnostic/reference only."
        ),
        "source_programmatic_access_status": probe.get("assessment", {}).get("status"),
    }


def _select_entrypoint_validation_candidates(
    candidates: list[dict[str, Any]],
    *,
    export_name: str | None,
    command_id: int | str | None,
) -> list[dict[str, Any]]:
    selected = candidates
    if export_name:
        requested = export_name.casefold()
        selected = [
            candidate
            for candidate in selected
            if str(candidate.get("export", "")).casefold() == requested
        ]
    if command_id is not None:
        try:
            requested_command = int(command_id)
        except (TypeError, ValueError):
            requested_command = None
        selected = [
            candidate
            for candidate in selected
            if requested_command is not None and candidate.get("command_id") == requested_command
        ]
    return [_entrypoint_validation_candidate_summary(candidate) for candidate in selected[:10]]


def _entrypoint_validation_candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "export": candidate.get("export"),
        "relative_path": candidate.get("relative_path"),
        "file": candidate.get("file"),
        "architecture": candidate.get("architecture"),
        "machine": candidate.get("machine"),
        "spring_kind": candidate.get("spring_kind"),
        "command_id": candidate.get("command_id"),
        "command_title": candidate.get("command_title"),
        "confidence": candidate.get("confidence"),
        "callability": candidate.get("callability"),
        "production_safe": False,
        "risk": candidate.get("risk"),
    }


def _entrypoint_validation_assessment(dossier: dict[str, Any], selected: list[dict[str, Any]]) -> dict[str, Any]:
    if not dossier.get("candidate_count"):
        status = "no_entrypoint_candidates"
    elif not selected:
        status = "no_candidate_selected"
    else:
        status = "isolated_validation_plan_ready"
    return {
        "status": status,
        "may_call_export_now": False,
        "production_bridge_allowed": False,
        "full_autonomous_access_supported": False,
        "public_callable_contract_detected": False,
        "requires_isolated_process": bool(selected),
        "requires_explicit_operator_approval": bool(selected),
        "verdict": (
            "This plan is only a reverse-engineering harness specification. "
            "It does not validate Spring as an autonomous production API."
        ),
        "hard_blocks": [
            "Never call an unknown native export from the production MCP bridge process.",
            "Never run the harness with open user documents or unsaved KOMPAS state.",
            "Do not promote a candidate without a repeatable signature, input/output, ownership, threading, and error contract.",
        ],
        "promotion_gates": [
            "Static ABI inventory identifies architecture, dependencies, export ordinal/name, and plausible calling convention.",
            "Isolated LoadLibrary/GetProcAddress probe exits cleanly without touching KOMPAS documents.",
            "A no-op or documented introspection call is demonstrated repeatedly in a throwaway process.",
            "A minimal input/output contract is documented and covered by crash-contained tests.",
            "Only then consider a separate experimental adapter; production remains disabled by default.",
        ],
        "fallback": (
            "If these gates fail, use an owned autonomous spring calculation/modeling path and keep native Spring as a reference tool."
        ),
    }


def _entrypoint_validation_harness(selected: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "mode": "specification_only_no_execution",
        "selected_exports": [
            {
                "dll": candidate.get("relative_path") or candidate.get("file"),
                "export": candidate.get("export"),
                "architecture": candidate.get("architecture") or "unknown",
                "command_id": candidate.get("command_id"),
                "spring_kind": candidate.get("spring_kind"),
            }
            for candidate in selected
        ],
        "phases": [
            {
                "name": "static_abi_inventory",
                "allowed_actions": [
                    "parse PE headers and export table",
                    "inspect imports/dependencies with static tools",
                    "record architecture and decorated/undecorated export names",
                ],
                "blocked_actions": ["LoadLibrary", "GetProcAddress", "calling the export"],
                "expected_evidence": ["machine architecture", "export name/ordinal", "dependency list"],
            },
            {
                "name": "isolated_loader_probe",
                "allowed_actions": [
                    "spawn a throwaway process",
                    "set an empty temporary working directory",
                    "LoadLibrary and GetProcAddress only",
                    "exit immediately after resolving addresses",
                ],
                "blocked_actions": ["calling unresolved exports", "opening user documents", "running inside MCP bridge"],
                "expected_evidence": ["load status", "GetProcAddress status", "process exit code"],
            },
            {
                "name": "signature_validation",
                "allowed_actions": [
                    "test only after a plausible signature is documented",
                    "use crash containment and timeout",
                    "start with no-op/introspection style calls only",
                ],
                "blocked_actions": ["passing guessed structs into production files", "saving documents", "batch execution"],
                "expected_evidence": ["repeatable return value", "stable error handling", "no document side effects"],
            },
        ],
        "default_timeout_seconds": 10,
        "recommended_workdir_policy": "new_empty_temp_dir_per_run",
        "result_policy": "write bounded JSON result plus process exit code; never rely on UI state",
    }


def _pe_static_abi_inventory(
    path: Path,
    *,
    selected_export: str,
    max_exports: int,
    max_import_dlls: int,
    max_imports_per_dll: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "is_pe": False,
        "architecture": None,
        "machine": None,
        "selected_export": selected_export,
        "selected_export_found": False,
        "exports": [],
        "imports": [],
        "dependencies": [],
    }
    try:
        data = path.read_bytes()
    except OSError as exc:
        payload["error"] = str(exc)
        return payload
    layout = _pe_layout(data)
    if not layout.get("ok"):
        payload.update(layout)
        return payload

    exports = _pe_export_inventory(
        data,
        layout,
        max_exports=max_exports,
        selected_export=selected_export,
    )
    imports = _pe_import_inventory(
        data,
        layout,
        max_import_dlls=max_import_dlls,
        max_imports_per_dll=max_imports_per_dll,
    )
    selected = exports.get("selected_export")
    payload.update(
        {
            "ok": True,
            "is_pe": True,
            "machine": layout.get("machine"),
            "architecture": layout.get("architecture"),
            "pe_kind": layout.get("pe_kind"),
            "export_count": exports.get("export_count", 0),
            "exports_returned": len(exports.get("exports", [])),
            "exports_truncated": exports.get("truncated", False),
            "selected_export_found": selected is not None,
            "selected_export_entry": selected,
            "imports": imports.get("imports", []),
            "dependencies": imports.get("dependencies", []),
            "import_dll_count": imports.get("import_dll_count", 0),
            "imports_truncated": imports.get("truncated", False),
            "evidence": [
                "parsed_dos_header",
                "parsed_pe_header",
                "parsed_export_table" if exports.get("available") else "no_export_table",
                "parsed_import_table" if imports.get("available") else "no_import_table",
            ],
        }
    )
    return payload


def _pe_layout(data: bytes) -> dict[str, Any]:
    if len(data) < 0x40 or data[:2] != b"MZ":
        return {"ok": False, "is_pe": False, "error": "not a PE/MZ file"}
    try:
        pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe_offset : pe_offset + 4] != b"PE\0\0":
            return {"ok": False, "is_pe": False, "error": "PE signature not found"}
        coff = pe_offset + 4
        machine = struct.unpack_from("<H", data, coff)[0]
        section_count = struct.unpack_from("<H", data, coff + 2)[0]
        optional_size = struct.unpack_from("<H", data, coff + 16)[0]
        optional = coff + 20
        magic = struct.unpack_from("<H", data, optional)[0]
        if magic == 0x10B:
            data_directory = optional + 96
            pointer_size = 4
            ordinal_flag = 0x80000000
            pe_kind = "PE32"
        elif magic == 0x20B:
            data_directory = optional + 112
            pointer_size = 8
            ordinal_flag = 0x8000000000000000
            pe_kind = "PE32+"
        else:
            return {"ok": False, "is_pe": True, "error": "unknown PE optional header magic"}
        directories = []
        for index in range(16):
            offset = data_directory + index * 8
            rva, size = struct.unpack_from("<II", data, offset)
            directories.append({"rva": rva, "size": size})
        sections = []
        section_offset = optional + optional_size
        for index in range(section_count):
            offset = section_offset + index * 40
            name = data[offset : offset + 8].rstrip(b"\0").decode("ascii", errors="replace")
            virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", data, offset + 8)
            sections.append(
                {
                    "name": name,
                    "virtual_address": virtual_address,
                    "virtual_size": max(virtual_size, raw_size),
                    "raw_pointer": raw_pointer,
                    "raw_size": raw_size,
                }
            )
        return {
            "ok": True,
            "is_pe": True,
            "machine": f"0x{machine:04X}",
            "architecture": _pe_machine_architecture(machine),
            "pe_kind": pe_kind,
            "pointer_size": pointer_size,
            "ordinal_flag": ordinal_flag,
            "directories": directories,
            "sections": sections,
        }
    except (IndexError, struct.error, ValueError) as exc:
        return {"ok": False, "is_pe": False, "error": f"PE header parse failed: {exc}"}


def _pe_export_inventory(
    data: bytes,
    layout: dict[str, Any],
    *,
    max_exports: int,
    selected_export: str,
) -> dict[str, Any]:
    export_dir = layout["directories"][0]
    export_rva = int(export_dir.get("rva") or 0)
    export_size = int(export_dir.get("size") or 0)
    if export_rva == 0:
        return {"available": False, "export_count": 0, "exports": [], "selected_export": None, "truncated": False}
    sections = _pe_sections_as_tuples(layout)
    export_offset = _pe_rva_to_offset(export_rva, sections)
    if export_offset is None:
        return {"available": False, "export_count": 0, "exports": [], "selected_export": None, "truncated": False}
    try:
        ordinal_base = struct.unpack_from("<I", data, export_offset + 16)[0]
        function_count = struct.unpack_from("<I", data, export_offset + 20)[0]
        name_count = struct.unpack_from("<I", data, export_offset + 24)[0]
        functions_rva = struct.unpack_from("<I", data, export_offset + 28)[0]
        names_rva = struct.unpack_from("<I", data, export_offset + 32)[0]
        ordinals_rva = struct.unpack_from("<I", data, export_offset + 36)[0]
        functions_offset = _pe_rva_to_offset(functions_rva, sections)
        names_offset = _pe_rva_to_offset(names_rva, sections)
        ordinals_offset = _pe_rva_to_offset(ordinals_rva, sections)
        if functions_offset is None or names_offset is None or ordinals_offset is None:
            return {"available": False, "export_count": name_count, "exports": [], "selected_export": None, "truncated": False}
        exports = []
        selected_entry = None
        selected_key = selected_export.casefold()
        for index in range(min(name_count, max_exports)):
            name_rva = struct.unpack_from("<I", data, names_offset + index * 4)[0]
            name_offset = _pe_rva_to_offset(name_rva, sections)
            ordinal_index = struct.unpack_from("<H", data, ordinals_offset + index * 2)[0]
            function_rva = (
                struct.unpack_from("<I", data, functions_offset + ordinal_index * 4)[0]
                if ordinal_index < function_count
                else None
            )
            name = _read_c_string(data, name_offset) if name_offset is not None else ""
            forwarded = (
                function_rva is not None
                and export_rva <= function_rva < export_rva + export_size
            )
            entry = {
                "name": name,
                "ordinal": ordinal_base + ordinal_index,
                "ordinal_index": ordinal_index,
                "rva": f"0x{function_rva:08X}" if function_rva is not None else None,
                "forwarded": forwarded,
            }
            exports.append(entry)
            if selected_key and name.casefold() == selected_key:
                selected_entry = entry
        return {
            "available": True,
            "export_count": name_count,
            "exports": exports,
            "selected_export": selected_entry,
            "truncated": name_count > max_exports,
        }
    except (IndexError, struct.error, ValueError) as exc:
        return {"available": False, "export_count": 0, "exports": [], "selected_export": None, "error": str(exc)}


def _pe_import_inventory(
    data: bytes,
    layout: dict[str, Any],
    *,
    max_import_dlls: int,
    max_imports_per_dll: int,
) -> dict[str, Any]:
    import_dir = layout["directories"][1]
    import_rva = int(import_dir.get("rva") or 0)
    if import_rva == 0:
        return {"available": False, "import_dll_count": 0, "dependencies": [], "imports": [], "truncated": False}
    sections = _pe_sections_as_tuples(layout)
    descriptor_offset = _pe_rva_to_offset(import_rva, sections)
    if descriptor_offset is None:
        return {"available": False, "import_dll_count": 0, "dependencies": [], "imports": [], "truncated": False}
    imports = []
    truncated = False
    pointer_size = int(layout["pointer_size"])
    ordinal_flag = int(layout["ordinal_flag"])
    try:
        descriptor_index = 0
        while descriptor_index < max_import_dlls:
            offset = descriptor_offset + descriptor_index * 20
            original_first_thunk, _time, _forwarder, name_rva, first_thunk = struct.unpack_from("<IIIII", data, offset)
            if original_first_thunk == 0 and name_rva == 0 and first_thunk == 0:
                break
            name_offset = _pe_rva_to_offset(name_rva, sections)
            dll_name = _read_c_string(data, name_offset) if name_offset is not None else ""
            thunk_rva = original_first_thunk or first_thunk
            symbols = _pe_import_symbols(
                data,
                sections,
                thunk_rva=thunk_rva,
                pointer_size=pointer_size,
                ordinal_flag=ordinal_flag,
                max_symbols=max_imports_per_dll,
            )
            imports.append(
                {
                    "dll": dll_name,
                    "symbol_count_returned": len(symbols["symbols"]),
                    "symbols_truncated": symbols["truncated"],
                    "symbols": symbols["symbols"],
                }
            )
            if symbols["truncated"]:
                truncated = True
            descriptor_index += 1
        if descriptor_index >= max_import_dlls:
            truncated = True
        return {
            "available": True,
            "import_dll_count": len(imports),
            "dependencies": [item["dll"] for item in imports],
            "imports": imports,
            "truncated": truncated,
        }
    except (IndexError, struct.error, ValueError) as exc:
        return {"available": False, "import_dll_count": 0, "dependencies": [], "imports": [], "truncated": False, "error": str(exc)}


def _pe_import_symbols(
    data: bytes,
    sections: list[tuple[int, int, int, int]],
    *,
    thunk_rva: int,
    pointer_size: int,
    ordinal_flag: int,
    max_symbols: int,
) -> dict[str, Any]:
    thunk_offset = _pe_rva_to_offset(thunk_rva, sections)
    if thunk_offset is None:
        return {"symbols": [], "truncated": False}
    symbols = []
    step_format = "<Q" if pointer_size == 8 else "<I"
    ordinal_mask = ordinal_flag - 1
    for index in range(max_symbols):
        thunk_value = struct.unpack_from(step_format, data, thunk_offset + index * pointer_size)[0]
        if thunk_value == 0:
            return {"symbols": symbols, "truncated": False}
        if thunk_value & ordinal_flag:
            symbols.append({"ordinal": int(thunk_value & ordinal_mask)})
            continue
        hint_name_offset = _pe_rva_to_offset(int(thunk_value), sections)
        if hint_name_offset is None:
            symbols.append({"name": None, "hint": None})
            continue
        hint = struct.unpack_from("<H", data, hint_name_offset)[0]
        symbols.append({"name": _read_c_string(data, hint_name_offset + 2), "hint": hint})
    return {"symbols": symbols, "truncated": True}


def _pe_sections_as_tuples(layout: dict[str, Any]) -> list[tuple[int, int, int, int]]:
    return [
        (
            int(section["virtual_address"]),
            int(section["virtual_size"]),
            int(section["raw_pointer"]),
            int(section["raw_size"]),
        )
        for section in layout.get("sections", [])
    ]


def _static_abi_entry_readiness(candidate: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    selected_found = bool(inventory.get("selected_export_found"))
    imports_available = bool(inventory.get("imports"))
    return {
        "status": "static_abi_inventory_complete" if inventory.get("ok") and selected_found else "static_abi_inventory_incomplete",
        "export_found": selected_found,
        "imports_available": imports_available,
        "architecture_matches_candidate": (
            inventory.get("architecture") == candidate.get("architecture")
            if inventory.get("architecture") and candidate.get("architecture")
            else None
        ),
        "may_advance_to_loader_probe": False,
        "reason": (
            "Static ABI evidence is ready for human review; loader probing still requires explicit approval."
            if inventory.get("ok") and selected_found
            else "Selected export was not proven in the static PE table."
        ),
    }


def _static_abi_inventory_assessment(entries: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any]:
    complete = [entry for entry in entries if entry.get("readiness", {}).get("status") == "static_abi_inventory_complete"]
    return {
        "status": "static_abi_inventory_complete" if complete and len(complete) == len(entries) else "static_abi_inventory_needs_review",
        "complete_entry_count": len(complete),
        "entry_count": len(entries),
        "may_call_export_now": False,
        "production_bridge_allowed": False,
        "full_autonomous_access_supported": False,
        "next_gate": "isolated_loader_probe" if complete else "fix_static_inventory_or_selection",
        "verdict": (
            "Static PE data can narrow the reverse-engineering target, but it still does not define a callable Spring API."
        ),
        "hard_blocks": plan.get("assessment", {}).get("hard_blocks", []),
    }


def _spring_calculation_workflow(inspection: dict[str, Any]) -> dict[str, Any]:
    spring = inspection.get("spring") or {}
    commands: list[dict[str, Any]] = []
    capability_counts = {
        "design_calculation": 0,
        "verification_calculation": 0,
        "result_report": 0,
        "build_model_or_drawing": 0,
        "build_without_calculation": 0,
    }
    for command in spring.get("commands", []):
        help_text = " ".join(
            str(command.get(key) or "")
            for key in ("summary", "method", "build_without_calculation")
        ).lower()
        workflow = list(command.get("workflow") or [])
        if command.get("build_without_calculation"):
            capability_counts["build_without_calculation"] += 1
        for capability in capability_counts:
            if capability in workflow:
                capability_counts[capability] += 1
        commands.append(
            {
                "id": command.get("id"),
                "title": command.get("title"),
                "help_key": command.get("help_key"),
                "workflow": workflow,
                "descriptions": {
                    "summary": command.get("summary"),
                    "method": command.get("method"),
                    "build_without_calculation": command.get("build_without_calculation"),
                },
                "evidence": {
                    "mentions_design": "design" in help_text or "проект" in help_text,
                    "mentions_verification": "verification" in help_text or "провер" in help_text,
                    "mentions_model_or_drawing": (
                        "model" in help_text
                        or "drawing" in help_text
                        or "модел" in help_text
                        or "черт" in help_text
                    ),
                },
                "likely_reference_groups": _spring_command_reference_groups(command.get("id")),
            }
        )
    return {
        "commands": commands,
        "capabilities": {
            "design_calculation_commands": capability_counts["design_calculation"],
            "verification_calculation_commands": capability_counts["verification_calculation"],
            "result_report_commands": capability_counts["result_report"],
            "build_model_or_drawing_commands": capability_counts["build_model_or_drawing"],
            "build_without_calculation_mentions": capability_counts["build_without_calculation"],
            "notes": [
                "Capabilities are derived from Spring help DB and command metadata; they describe user workflow, not a parameter API.",
            ],
        },
    }


def _spring_reference_database_map(
    inventory: list[dict[str, Any]],
    *,
    max_sample_rows: int,
) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    databases: list[dict[str, Any]] = []
    for database in inventory:
        database_groups: dict[str, int] = {}
        table_payloads = []
        db_path = Path(str(database.get("path") or ""))
        for table in database.get("tables", []):
            group = _classify_spring_table(str(table.get("name") or ""))
            group_payload = groups.setdefault(
                group,
                {
                    "table_count": 0,
                    "total_rows": 0,
                    "tables": [],
                    "truncated": False,
                },
            )
            row_count = table.get("row_count")
            group_payload["table_count"] += 1
            if isinstance(row_count, int):
                group_payload["total_rows"] += row_count
            table_summary = {
                "name": table.get("name"),
                "database": database.get("name"),
                "row_count": row_count,
                "columns": table.get("columns", [])[:16],
            }
            if len(group_payload["tables"]) < 12:
                table_summary["sample_rows"] = _sqlite_table_sample(
                    db_path,
                    str(table.get("name") or ""),
                    max_rows=max_sample_rows,
                    columns=table.get("columns", [])[:8],
                )
                group_payload["tables"].append(table_summary)
            else:
                group_payload["truncated"] = True
            database_groups[group] = database_groups.get(group, 0) + 1
            table_payloads.append(
                {
                    "name": table.get("name"),
                    "group": group,
                    "row_count": row_count,
                    "columns": table.get("columns", [])[:16],
                }
            )
        databases.append(
            {
                "name": database.get("name"),
                "ok": database.get("ok"),
                "table_count": database.get("table_count"),
                "groups": database_groups,
                "tables": table_payloads[:80],
                "truncated": bool(database.get("truncated")) or len(table_payloads) > 80,
            }
        )
    return {
        "database_count": len(databases),
        "databases": databases,
        "groups": groups,
        "notes": [
            "These SQLite/SDB databases are mapped as reference/calculation data.",
            "No table in this map is treated as a supported session or job-file contract by itself.",
        ],
    }


def _classify_spring_table(name: str) -> str:
    upper = name.upper()
    if upper in {"VERSION", "SPRVID", "SQLITE_SEQUENCE"}:
        return "metadata"
    if upper.startswith("DISKSPRING") or upper.startswith("SPRCPS"):
        return "disc_spring_reference"
    if upper.startswith("SPRCON"):
        return "conical_spring_reference"
    if upper.endswith("_CRS") or "_CRS" in upper:
        return "torsion_spring_reference"
    if upper.endswith("_CES") or "_CES" in upper:
        return "extension_spring_reference"
    if upper.startswith("SPRPARAMSCOILS"):
        return "coil_spring_design_tables"
    if "MATERIAL" in upper or upper.startswith("RM_") or upper.startswith("SORT") or upper == "SPCES":
        return "material_strength_reference"
    if upper.startswith("DOPUSK") or upper.startswith("IT_") or upper.startswith("BORDER_"):
        return "tolerance_reference"
    return "other_reference"


def _spring_command_reference_groups(command_id: Any) -> list[str]:
    mapping = {
        "101": ["coil_spring_design_tables", "material_strength_reference", "tolerance_reference"],
        "102": ["extension_spring_reference", "material_strength_reference", "tolerance_reference"],
        "103": ["disc_spring_reference", "material_strength_reference", "tolerance_reference"],
        "104": ["conical_spring_reference", "material_strength_reference", "tolerance_reference"],
        "105": ["torsion_spring_reference", "material_strength_reference", "tolerance_reference"],
    }
    return mapping.get(str(command_id), ["other_reference"])


def _sqlite_table_sample(
    database_path: Path,
    table_name: str,
    *,
    max_rows: int,
    columns: list[str],
) -> list[dict[str, Any]]:
    if not database_path.is_file() or not table_name or max_rows <= 0:
        return []
    safe_columns = [column for column in columns if column]
    if not safe_columns:
        return []
    selected_columns = safe_columns[: min(len(safe_columns), 6)]
    quoted_table = _quote_sqlite_identifier(table_name)
    quoted_columns = ", ".join(_quote_sqlite_identifier(column) for column in selected_columns)
    connection = None
    try:
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
        rows = connection.execute(
            f"select {quoted_columns} from {quoted_table} limit ?",
            (max_rows,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        if connection is not None:
            connection.close()
    return [
        {column: row[index] for index, column in enumerate(selected_columns)}
        for row in rows
    ]


def _spring_workflow_automation_assessment(reference_map: dict[str, Any]) -> dict[str, Any]:
    groups = reference_map.get("groups", {})
    has_reference_data = bool(groups)
    has_design_tables = any(
        group in groups
        for group in (
            "coil_spring_design_tables",
            "disc_spring_reference",
            "conical_spring_reference",
            "extension_spring_reference",
            "torsion_spring_reference",
        )
    )
    return {
        "status": "reference_workflow_mapped_no_public_parameter_contract",
        "reference_data_detected": has_reference_data,
        "calculation_tables_detected": has_design_tables,
        "public_parameter_contract_detected": False,
        "safe_to_use_for_automation": False,
        "recommended_boundary": (
            "Use Spring through interactive native commands until a supported "
            "job/session/interface contract is proven."
        ),
        "limits": [
            "Reference tables can explain Spring choices but are not the Spring solver contract.",
            "Writing to Spring databases is intentionally out of scope.",
            "Manual before/after probing is still required to prove model or drawing results.",
        ],
    }


def _spring_interface_summary(inspection: dict[str, Any]) -> dict[str, Any]:
    spring = inspection.get("spring") or {}
    commands = spring.get("commands", [])
    return {
        "module_kind": spring.get("module_kind", "calculation_workflow"),
        "workflow_layers": [
            "interactive_launch",
            "manual_calculation_session",
            "model_or_drawing_creation",
            "post_workflow_readback",
        ],
        "commands": commands,
        "automation_boundary": (
            "compression_spring remains an intent/preview contract until a supported "
            "Spring parameter/session interface is found."
        ),
    }


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return True


def _quote_sqlite_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _spring_module_summary(module_dir: Path, commands: list[dict[str, Any]]) -> dict[str, Any]:
    localized = _spring_localized_help(module_dir)
    command_modes = []
    for command in commands:
        command_id = command.get("id")
        help_row = localized.get(command_id, {})
        command_modes.append(
            {
                "id": command_id,
                "title": command.get("title"),
                "help_key": help_row.get("help_key"),
                "summary": help_row.get("summary"),
                "method": help_row.get("method"),
                "build_without_calculation": help_row.get("build_without_calculation"),
                "workflow": [
                    "design_calculation",
                    "verification_calculation",
                    "result_report",
                    "build_model_or_drawing",
                ],
            }
        )
    return {
        "module_kind": "calculation_workflow",
        "commands": command_modes,
        "notes": [
            "The Spring module is treated as a native calculation workflow, not as a custom geometry builder.",
            "This MCP layer currently discovers files, commands, and databases only; command launch and parameter automation are separate steps.",
        ],
    }


def _spring_localized_help(module_dir: Path) -> dict[int, dict[str, Any]]:
    help_db = module_dir / "SPRING_ru-RU.db"
    if not help_db.is_file():
        return {}
    connection = None
    try:
        connection = sqlite3.connect(f"file:{help_db}?mode=ro", uri=True)
        id_rows = connection.execute("select Id, Name from Ids").fetchall()
        help_by_key = {
            row[0]: row
            for row in connection.execute("select Id, D1, D2, D3 from Help").fetchall()
        }
    except sqlite3.Error:
        return {}
    finally:
        if connection is not None:
            connection.close()

    payload: dict[int, dict[str, Any]] = {}
    for command_id, help_key in id_rows:
        row = help_by_key.get(help_key)
        if row is None:
            continue
        payload[int(command_id)] = {
            "help_key": help_key,
            "summary": row[1],
            "method": row[2],
            "build_without_calculation": row[3],
        }
    return payload


def _normalize_limit(value: int | None, *, default: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    if normalized <= 0:
        return default
    return min(normalized, maximum)


def _has_more_module_manifests(libs_dir: Path, returned_count: int) -> bool:
    count = 0
    for module_dir in libs_dir.iterdir():
        if module_dir.is_dir() and _find_module_manifest(module_dir) is not None:
            count += 1
            if count > returned_count:
                return True
    return False
