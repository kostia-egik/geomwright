from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.batch import scan_model_files


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.documents: list[dict] = []

    def call(self, action: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        self.calls.append((action, payload))

        if action == "list_documents":
            return {"documents": list(self.documents)}

        if action == "open_document":
            path = payload["path"]
            document = {"id": path, "name": Path(path).name, "path": path, "active": True}
            self.documents = [document]
            return {"document": document}

        if action == "save_document":
            target_path = payload.get("path")
            if target_path:
                Path(target_path).parent.mkdir(parents=True, exist_ok=True)
                Path(target_path).write_bytes(b"smoke")
            if payload.get("close_after_save"):
                self.documents = []
            return {
                "document": {"id": payload.get("document_id"), "path": payload.get("document_id")},
                "saved_as": target_path,
                "closed": bool(payload.get("close_after_save")),
            }

        if action == "close_document":
            document_id = payload.get("document_id")
            self.documents = [
                document
                for document in self.documents
                if document_id not in (document.get("id"), document.get("path"), document.get("name"))
            ]
            return {"document": {"id": document_id}, "closed": True}

        if action == "get_document_tree":
            document_id = payload.get("document_id")
            return {
                "document": {"id": document_id, "name": Path(str(document_id)).name, "path": document_id},
                "tree": {
                    "id": "root",
                    "name": " Assembly  ",
                    "designation": "ASM-001",
                    "title": "Assembly",
                    "material": "Steel",
                    "children": [
                        {
                            "id": "root/0",
                            "name": " Part  ",
                            "designation": "",
                            "title": "",
                            "material": "",
                            "kind": "part",
                            "children": [],
                        }
                    ],
                },
            }

        raise AssertionError(f"Unexpected bridge action: {action}")


class BatchTests(unittest.TestCase):
    def test_open_document_uses_source_path_normalizer(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)
        original = KompasAdapter._normalize_path_for_kompas

        try:
            KompasAdapter._normalize_path_for_kompas = staticmethod(lambda path: "SHORT::" + Path(path).name)
            with tempfile.TemporaryDirectory() as temp_dir:
                source = Path(temp_dir) / "very long source name.a3d"
                source.write_bytes(b"a3d")

                adapter.open_document(str(source), visible=False, read_only=True)
        finally:
            KompasAdapter._normalize_path_for_kompas = staticmethod(original)

        open_calls = [payload for action, payload in runner.calls if action == "open_document"]
        self.assertEqual(open_calls[0]["path"], "SHORT::very long source name.a3d")

    def test_save_document_as_preserves_long_target_name(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)
        original_short = KompasAdapter._normalize_path_for_kompas
        original_long = KompasAdapter._normalize_long_path_for_kompas

        try:
            KompasAdapter._normalize_path_for_kompas = staticmethod(lambda path: str(Path(path).with_name("SHORT~1")))
            KompasAdapter._normalize_long_path_for_kompas = staticmethod(lambda path: str(Path(path)))
            with tempfile.TemporaryDirectory() as temp_dir:
                target = Path(temp_dir) / "very long target name.m3d"
                adapter.save_document_as(str(target), document_id="doc-1", close_after_save=False)
        finally:
            KompasAdapter._normalize_path_for_kompas = staticmethod(original_short)
            KompasAdapter._normalize_long_path_for_kompas = staticmethod(original_long)

        save_calls = [payload for action, payload in runner.calls if action == "save_document"]
        self.assertEqual(Path(save_calls[0]["path"]).name, "very long target name.m3d")

    def test_scan_model_files_filters_extensions_and_locks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "assembly.a3d").write_bytes(b"a3d")
            (root / "part.m3d").write_bytes(b"m3d")
            (root / "~$locked.a3d").write_bytes(b"lock")
            (root / "note.txt").write_text("skip", encoding="utf-8")

            result = scan_model_files(str(root))

        self.assertEqual(result["summary"]["file_count"], 2)
        self.assertEqual(result["summary"]["skipped_by_reason"]["lock_file"], 1)
        self.assertEqual(result["summary"]["skipped_by_reason"]["unsupported_extension"], 1)
        self.assertEqual(result["summary"]["by_extension"], {".a3d": 1, ".m3d": 1})

    def test_batch_smoke_check_supports_dry_run(self) -> None:
        adapter = KompasAdapter(runner=FakeRunner())

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "assembly.a3d").write_bytes(b"a3d")
            (root / "part.m3d").write_bytes(b"m3d")

            result = adapter.batch_smoke_check_session(root=str(root), dry_run=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["dry_run_count"], 2)
        self.assertEqual(result["summary"]["processed_count"], 2)

    def test_batch_smoke_check_runs_over_explicit_paths(self) -> None:
        adapter = KompasAdapter(runner=FakeRunner())

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "assembly.a3d"
            second = root / "part.m3d"
            first.write_bytes(b"a3d")
            second.write_bytes(b"m3d")

            result = adapter.batch_smoke_check_session(paths=[str(first), str(second)], output_dir=temp_dir)

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["ok_count"], 2)
        self.assertEqual(result["summary"]["error_count"], 0)
        self.assertEqual(result["summary"]["candidate_count"], 2)

    def test_batch_analyze_model_quality_opens_readonly_and_closes(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "assembly.a3d"
            first.write_bytes(b"a3d")

            result = adapter.batch_analyze_model_quality(paths=[str(first)], rules={})

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["ok_count"], 1)
        self.assertGreater(result["summary"]["total_issues"], 0)
        self.assertIn("naming", result["results"][0]["analyses"])
        self.assertIn("spec", result["results"][0]["analyses"])
        open_calls = [payload for action, payload in runner.calls if action == "open_document"]
        self.assertTrue(open_calls[0]["read_only"])
        self.assertEqual(runner.documents, [])

    def test_batch_smoke_check_can_write_json_and_markdown_report(self) -> None:
        adapter = KompasAdapter(runner=FakeRunner())

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_dir = root / "reports"
            first = root / "assembly.a3d"
            first.write_bytes(b"a3d")

            result = adapter.batch_smoke_check_session(
                paths=[str(first)],
                output_dir=temp_dir,
                report_dir=str(report_dir),
                report_name="smoke-report",
            )

            json_path = report_dir / "smoke-report.json"
            markdown_path = report_dir / "smoke-report.md"
            json_exists = json_path.exists()
            markdown_exists = markdown_path.exists()
            json_payload = json.loads(json_path.read_text(encoding="utf-8-sig"))

        self.assertTrue(result["report"]["ok"])
        self.assertTrue(json_exists)
        self.assertTrue(markdown_exists)
        self.assertEqual(json_payload["report_type"], "batch_smoke_check")
        self.assertEqual(json_payload["summary"]["ok_count"], 1)

    def test_batch_quality_report_can_be_limited_to_markdown(self) -> None:
        adapter = KompasAdapter(runner=FakeRunner())

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_dir = root / "reports"
            first = root / "assembly.a3d"
            first.write_bytes(b"a3d")

            result = adapter.batch_analyze_model_quality(
                paths=[str(first)],
                rules={},
                report_dir=str(report_dir),
                report_name="quality-report",
                report_formats=["md"],
            )

            markdown_path = report_dir / "quality-report.md"
            json_path = report_dir / "quality-report.json"
            markdown_exists = markdown_path.exists()
            json_exists = json_path.exists()
            markdown = markdown_path.read_text(encoding="utf-8-sig")

        self.assertTrue(result["report"]["ok"])
        self.assertTrue(markdown_exists)
        self.assertFalse(json_exists)
        self.assertIn("Batch Model Quality", markdown)
        self.assertIn("Total issues", markdown)


if __name__ == "__main__":
    unittest.main()
