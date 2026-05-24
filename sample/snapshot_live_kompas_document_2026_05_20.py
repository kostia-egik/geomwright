from __future__ import annotations

import argparse
import json

from kompas_mcp.adapter import KompasAdapter


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture a bounded KOMPAS document snapshot and optional full artifact.")
    parser.add_argument("--model-path", default=None, help="Open this model read-only before snapshotting.")
    parser.add_argument("--document-id", default=None, help="Snapshot an already opened document id.")
    parser.add_argument(
        "--output",
        default="sample/generated/live_kompas_document_snapshot_2026_05_20/snapshot.json",
        help="Full JSON artifact path.",
    )
    parser.add_argument("--visible", action="store_true", help="Open --model-path visibly.")
    parser.add_argument("--keep-open", action="store_true", help="Leave a model opened by this snapshot open.")
    parser.add_argument("--include-manifest", action="store_true", help="Also print the full manifest in the response.")
    args = parser.parse_args()

    adapter = KompasAdapter()
    result = adapter.capture_document_snapshot(
        model_path=args.model_path,
        document_id=args.document_id,
        output_path=args.output,
        visible=args.visible,
        read_only=True,
        close_after_probe=not args.keep_open,
        include_manifest=args.include_manifest,
    )
    snapshot = result.get("snapshot") or {}
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "status": result["status"],
                "summary": snapshot.get("summary"),
                "document": snapshot.get("document"),
                "artifact": snapshot.get("artifact"),
                "failures": result.get("failures", []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
