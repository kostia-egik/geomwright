from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.specification import resolve_spw_columns


BASE_FIELDS = ["position", "designation", "title", "quantity", "comment"]


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.documents: list[dict] = []

    def call(self, action: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        self.calls.append((action, payload))

        if action == "list_documents":
            if self.documents:
                return {"documents": list(self.documents)}
            return {"documents": [{"id": "doc-1", "name": "assembly.a3d", "path": r"C:\Temp\assembly.a3d", "active": True}]}

        if action == "open_document":
            path = payload["path"]
            document = {"id": path, "name": Path(path).name, "path": path, "active": True}
            self.documents = [document]
            return {"document": document, "open_attempts": [{"path": path, "returned_document": True}]}

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
            return {"document": {"id": document_id}, "saved": bool(payload.get("save")), "closed": True}

        if action == "get_document_tree":
            return {
                "document": {"id": "doc-1", "name": "assembly.a3d", "path": r"C:\Temp\assembly.a3d"},
                "tree": {
                    "id": "root",
                    "name": "Assembly",
                    "designation": "ASM-001",
                    "children": [
                        {
                            "id": "root/0",
                            "name": "Part",
                            "title": "Part",
                            "designation": "P-001",
                            "material": "Steel",
                            "mass": 2.5,
                            "volume": 10.0,
                            "density": 7.85,
                            "source_path": r"C:\Temp\part.a3d",
                            "kind": "part",
                            "children": [],
                        }
                    ],
                },
            }

        if action == "create_spw_from_rows":
            return {
                "created_count": len(payload["rows"]),
                "failed_count": 0,
                "spw_columns": payload["columns"],
            }

        raise AssertionError(f"Unexpected bridge action: {action}")


class SpwColumnTests(unittest.TestCase):
    def test_default_columns_are_base_only(self) -> None:
        plan = resolve_spw_columns()

        self.assertEqual([column["field"] for column in plan["columns"]], BASE_FIELDS)
        self.assertEqual(plan["ignored_columns"], [])
        self.assertEqual(plan["engineering_columns"], [])

    def test_engineering_column_is_ignored_without_opt_in(self) -> None:
        plan = resolve_spw_columns([{"field": "mass", "column_type": 7}])

        self.assertEqual(plan["columns"], [])
        self.assertEqual(plan["ignored_columns"][0]["field"], "mass")
        self.assertEqual(plan["ignored_columns"][0]["reason"], "engineering_requires_opt_in")

    def test_engineering_column_can_be_enabled_globally(self) -> None:
        plan = resolve_spw_columns(
            ["qty", {"field": "mass", "column_type": 7, "block_number": 2, "column_number": 5}],
            include_engineering=True,
        )

        self.assertEqual([column["field"] for column in plan["columns"]], ["quantity", "mass"])
        self.assertTrue(plan["columns"][0]["skip_unit_value"])
        self.assertEqual(plan["columns"][1]["block_number"], 2)
        self.assertEqual(plan["columns"][1]["column_number"], 5)

    def test_engineering_preset_is_explicit(self) -> None:
        plan = resolve_spw_columns(column_preset="engineering_comment_columns")

        self.assertEqual([column["field"] for column in plan["columns"][:5]], BASE_FIELDS)
        self.assertEqual([column["field"] for column in plan["engineering_columns"]], ["material", "mass", "volume"])

    def test_preview_reports_ignored_columns(self) -> None:
        adapter = KompasAdapter(runner=FakeRunner())
        preview = adapter.preview_spw_generation(columns=[*BASE_FIELDS, "mass"])

        self.assertEqual([column["field"] for column in preview["summary"]["spw_columns"]], BASE_FIELDS)
        self.assertEqual(preview["summary"]["spw_ignored_columns"][0]["field"], "mass")
        self.assertEqual(preview["summary"]["spw_column_report"]["engineering_column_count"], 0)

    def test_create_spw_passes_normalized_columns_to_bridge(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_spw_from_model(
            output_path=r"C:\Temp\unit-test.spw",
            columns=[
                *BASE_FIELDS,
                {"field": "mass", "column_type": 7, "block_number": 2, "column_number": 5, "allow_engineering": True},
            ],
        )

        create_calls = [payload for action, payload in runner.calls if action == "create_spw_from_rows"]
        self.assertEqual(len(create_calls), 1)
        payload = create_calls[0]
        self.assertEqual(payload["columns"][-1]["field"], "mass")
        self.assertEqual(payload["columns"][-1]["block_number"], 2)
        self.assertEqual(payload["columns"][-1]["column_number"], 5)
        self.assertEqual(payload["rows"][0]["mass"], 2.5)
        self.assertEqual(result["failed_count"], 0)

    def test_smoke_check_session_opens_saves_closes_and_checks_file(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.a3d"
            source.write_bytes(b"source")

            result = adapter.smoke_check_session(str(source), output_dir=temp_dir)

        actions = [action for action, _payload in runner.calls]
        self.assertIn("open_document", actions)
        self.assertIn("save_document", actions)
        self.assertIn("close_document", actions)
        self.assertTrue(result["ok"])
        self.assertEqual(result["remaining_target_documents"], [])
        self.assertTrue(result["saved_file_access"]["exclusive_open_ok"])


if __name__ == "__main__":
    unittest.main()
