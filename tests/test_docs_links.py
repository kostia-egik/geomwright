from __future__ import annotations

import re
import unittest
from pathlib import Path


LOCAL_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


class DocsLinksTests(unittest.TestCase):
    def test_markdown_local_file_links_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        docs_root = root / "docs"
        docs = [root / name for name in ("README.md", "ARCHITECTURE.md", "CAD_PATTERNS.md")]
        docs.extend(path for path in sorted(docs_root.rglob("*.md"))
                    if "archive" not in path.relative_to(docs_root).parts)
        missing: list[str] = []

        for doc in docs:
            text = doc.read_text(encoding="utf-8")
            for match in LOCAL_LINK_RE.finditer(text):
                target = match.group(1)
                if "://" in target or target.startswith("#") or target.startswith("mailto:"):
                    continue
                path_text = target.split("#", 1)[0]
                if not path_text:
                    continue
                candidate = (doc.parent / path_text).resolve()
                if not candidate.exists():
                    missing.append(f"{doc.relative_to(root)} -> {target}")

        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
