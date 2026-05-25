from __future__ import annotations

import os
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


DEFAULT_KOMPAS_ENV_VARS = ("KOMPAS_ROOT", "KOMPAS_INSTALL_DIR", "KOMPAS_HOME")
DEFAULT_MODULE_DATABASE_SUFFIXES = (".db", ".sdb")
DEFAULT_RUNTIME_SUFFIXES = (".dll", ".rtw")


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
