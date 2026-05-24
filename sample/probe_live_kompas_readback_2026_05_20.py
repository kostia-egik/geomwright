from __future__ import annotations

import argparse
import json

from kompas_mcp.adapter import KompasAdapter


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture a low-level KOMPAS readback probe manifest.")
    parser.add_argument("--model-path", default=None, help="Open this model read-only before probing.")
    parser.add_argument("--document-id", default=None, help="Probe an already opened document id.")
    parser.add_argument(
        "--output",
        default="sample/generated/live_kompas_readback_probe_2026_05_20/probe.json",
        help="JSON artifact path.",
    )
    parser.add_argument("--visible", action="store_true", help="Open --model-path visibly.")
    parser.add_argument("--keep-open", action="store_true", help="Leave a model opened by this probe open.")
    args = parser.parse_args()

    adapter = KompasAdapter()
    result = adapter.probe_document_readback(
        model_path=args.model_path,
        document_id=args.document_id,
        output_path=args.output,
        visible=args.visible,
        read_only=True,
        close_after_probe=not args.keep_open,
    )
    print(json.dumps({"ok": result["ok"], "summary": result["summary"], "artifact": result.get("artifact")}, indent=2))


if __name__ == "__main__":
    main()
