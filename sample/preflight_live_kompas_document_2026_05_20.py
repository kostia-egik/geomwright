from __future__ import annotations

import argparse
import json

from kompas_mcp.adapter import KompasAdapter


def main() -> None:
    parser = argparse.ArgumentParser(description="Check KOMPAS document readiness before low-level operations.")
    parser.add_argument("--document-id", default=None, help="Opened document id/path/name. Defaults to active document.")
    parser.add_argument("--expected-type", default=None, help="Expected KOMPAS document type, compared as text.")
    parser.add_argument(
        "--expected-extension",
        action="append",
        default=None,
        help="Allowed extension such as m3d/a3d/cdw. Can be passed more than once.",
    )
    parser.add_argument("--allow-non-active", action="store_true", help="Do not require the selected document to be active.")
    parser.add_argument("--require-tree", action="store_true", help="Read the document tree and require at least one node.")
    parser.add_argument("--require-items", action="store_true", help="Read flat items and require at least one item.")
    args = parser.parse_args()

    adapter = KompasAdapter()
    result = adapter.preflight_document_context(
        document_id=args.document_id,
        require_active_document=not args.allow_non_active,
        expected_document_type=args.expected_type,
        expected_extensions=args.expected_extension,
        require_tree=args.require_tree,
        require_items=args.require_items,
    )
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "document": result["document"],
                "readback": result["readback"],
                "failed_checks": [check for check in result["checks"] if not check["ok"]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
