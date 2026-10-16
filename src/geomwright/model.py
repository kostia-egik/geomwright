"""File/stdin CLI for the same module contract used by MCP."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from pydantic import ValidationError

from kompas_mcp.cad_modules import CadModuleRequest, get_cad_module_contract, run_cad_module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List implemented modules without CAD access")
    describe = commands.add_parser("describe", help="Get schemas, defaults and examples")
    describe.add_argument("module_id")
    run = commands.add_parser("run", help="Run a JSON request file, or - for stdin")
    run.add_argument("request")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            result = get_cad_module_contract()
        elif args.command == "describe":
            result = get_cad_module_contract(args.module_id)
        else:
            text = sys.stdin.read() if args.request == "-" else Path(args.request).read_text(encoding="utf-8-sig")
            request = CadModuleRequest.model_validate_json(text)
            # Only live actions need an adapter; importing it does not start CAD.
            adapter = None
            if request.action in ("create", "inspect"):
                from geomwright.kompas.adapter import KompasAdapter

                adapter = KompasAdapter()
            result = run_cad_module(request, adapter)
        code = 0 if result["ok"] else 1
    except (OSError, UnicodeError, ValidationError) as exc:
        result = {"ok": False, "error": {"code": "INVALID_REQUEST", "message": str(exc)[:2000]}}
        code = 2
    # ASCII JSON is Unicode-safe in Windows console pipes; JSON readers restore text.
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
