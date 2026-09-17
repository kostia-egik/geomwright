from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / "experiments" / "standards"


def _fitz() -> Any:
    try:
        import fitz  # type: ignore
    except ModuleNotFoundError as exc:
        raise SystemExit("PyMuPDF is required: python -m pip install pymupdf") from exc
    return fitz


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": 1, "documents": {}}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {"schema": 1, "documents": {}}


def _parse_topics(values: list[str]) -> dict[str, re.Pattern[str]]:
    topics: dict[str, re.Pattern[str]] = {}
    for value in values:
        name, separator, pattern = value.partition("=")
        if not separator or not name.strip() or not pattern:
            raise SystemExit("--topic must be NAME=REGEX")
        topics[name.strip()] = re.compile(pattern, re.IGNORECASE)
    return topics


def _split_pages(text: str) -> list[str]:
    parts = re.split(r"\n--- PDF PAGE \d+ ---\n", text)
    return parts[1:] if len(parts) > 1 else []


def _topic_pages(page_texts: list[str], topics: dict[str, re.Pattern[str]]) -> dict[str, list[int]]:
    return {
        name: [number for number, text in enumerate(page_texts, 1) if pattern.search(text)]
        for name, pattern in topics.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cache PDF standards text by SHA-256")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--topic", action="append", default=[], help="NAME=REGEX; record matching page numbers")
    args = parser.parse_args()

    fitz = _fitz()
    cache_root = args.cache_root if args.cache_root.is_absolute() else ROOT / args.cache_root
    text_root = cache_root / "text"
    text_root.mkdir(parents=True, exist_ok=True)
    index_path = cache_root / "index.json"
    index = _load_index(index_path)
    documents = index.setdefault("documents", {})
    topics = _parse_topics(args.topic)
    summary = []

    sources: list[Path] = []
    for raw in args.paths:
        path = raw if raw.is_absolute() else ROOT / raw
        if path.is_dir():
            sources.extend(sorted(path.glob("*.pdf")))
        elif path.suffix.lower() == ".pdf":
            sources.append(path)
    for source in sources:
        digest = _sha256(source)
        document_id = digest[:16]
        cached = documents.get(document_id) or {}
        cached_text = cached.get("text")
        text_path = cache_root / cached_text if isinstance(cached_text, str) else text_root / f"{document_id}-{source.stem}.txt"
        reused = cached.get("sha256") == digest and text_path.exists()
        if reused:
            pages = int(cached.get("pages") or 0)
            topic_pages = _topic_pages(_split_pages(text_path.read_text(encoding="utf-8")), topics) if topics else cached.get("topics") or {}
            cached["topics"] = topic_pages
        else:
            with fitz.open(source) as pdf:
                page_texts = [page.get_text() for page in pdf]
            pages = len(page_texts)
            text_path.write_text(
                "".join(f"\n--- PDF PAGE {number} ---\n{text}" for number, text in enumerate(page_texts, 1)),
                encoding="utf-8",
            )
            topic_pages = _topic_pages(page_texts, topics)
            documents[document_id] = {
                "filename": source.name,
                "sha256": digest,
                "pages": pages,
                "text": str(text_path.relative_to(cache_root)).replace("\\", "/"),
                "topics": topic_pages,
            }
        summary.append({"id": document_id, "filename": source.name, "pages": pages, "reused": reused, "topics": topic_pages})

    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "documents": summary, "index": str(index_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
