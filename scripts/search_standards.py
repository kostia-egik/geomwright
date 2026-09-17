from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "experiments" / "standards" / "index.json"
PAGE_MARKER = re.compile(r"\n--- PDF PAGE (\d+) ---\n")


def _bounded_int(minimum: int, maximum: int):
    def parse(value: str) -> int:
        number = int(value)
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
        return number

    return parse


def _pages(text: str) -> list[tuple[int, str]]:
    markers = list(PAGE_MARKER.finditer(text))
    return [
        (int(marker.group(1)), text[marker.end(): markers[index + 1].start() if index + 1 < len(markers) else len(text)])
        for index, marker in enumerate(markers)
    ]


def _excerpt(text: str, match: re.Match[str], context: int) -> str:
    start = max(0, match.start() - context)
    end = min(len(text), match.end() + context)
    return " ".join(text[start:end].split())


def main() -> int:
    parser = argparse.ArgumentParser(description="Search cached standards and return bounded page excerpts")
    parser.add_argument("query")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--document", help="Cached id or filename substring")
    parser.add_argument("--max-results", type=_bounded_int(1, 50), default=8)
    parser.add_argument("--context", type=_bounded_int(20, 1000), default=180)
    parser.add_argument("--literal", action="store_true")
    args = parser.parse_args()

    index_path = args.index if args.index.is_absolute() else ROOT / args.index
    index = json.loads(index_path.read_text(encoding="utf-8"))
    pattern = re.compile(re.escape(args.query) if args.literal else args.query, re.IGNORECASE)
    results = []
    for document_id, metadata in (index.get("documents") or {}).items():
        filename = str(metadata.get("filename") or "")
        if args.document and args.document.lower() not in (document_id + " " + filename).lower():
            continue
        text_path = index_path.parent / str(metadata["text"])
        for page, text in _pages(text_path.read_text(encoding="utf-8")):
            for match in pattern.finditer(text):
                results.append({"document": filename, "id": document_id, "page": page, "excerpt": _excerpt(text, match, args.context)})
                if len(results) >= args.max_results:
                    print(json.dumps({"ok": True, "result_count": len(results), "results": results}, ensure_ascii=False))
                    return 0
                break
    print(json.dumps({"ok": True, "result_count": len(results), "results": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
