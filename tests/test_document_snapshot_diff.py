import json
import tempfile
import unittest
from pathlib import Path

from kompas_mcp.document_snapshot_diff import diff_document_snapshots


class DocumentSnapshotDiffTests(unittest.TestCase):
    def test_reports_added_removed_changed_items_and_count_deltas(self) -> None:
        before = _manifest(
            [
                {"id": "root", "name": "Part", "source": "tree"},
                {"id": "sketch", "name": "Sketch", "source": "items", "visible": True},
                {"id": "old", "name": "Old", "source": "items"},
            ],
            items=3,
        )
        after = _manifest(
            [
                {"id": "root", "name": "Part", "source": "tree"},
                {"id": "sketch", "name": "Sketch", "source": "items", "visible": False},
                {"id": "new", "name": "New", "source": "items"},
            ],
            items=4,
        )

        result = diff_document_snapshots(before, after)

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["added_items"], 1)
        self.assertEqual(result["summary"]["removed_items"], 1)
        self.assertEqual(result["summary"]["changed_items"], 1)
        self.assertEqual(result["added"][0]["id"], "new")
        self.assertEqual(result["removed"][0]["id"], "old")
        self.assertEqual(result["changed"][0]["identity"], "id:sketch")
        self.assertEqual(result["counts_delta"]["items"]["delta"], 1)

    def test_accepts_snapshot_envelope_and_json_artifact_paths(self) -> None:
        before = {"snapshot": {"manifest": _manifest([{"id": "root", "name": "Part"}], items=1)}}
        after = {"manifest": _manifest([{"id": "root", "name": "Part"}, {"id": "line", "name": "Line"}], items=2)}

        with tempfile.TemporaryDirectory() as temp_dir:
            before_path = Path(temp_dir) / "before.json"
            after_path = Path(temp_dir) / "after.json"
            before_path.write_text(json.dumps(before), encoding="utf-8")
            after_path.write_text(json.dumps(after), encoding="utf-8")

            result = diff_document_snapshots(before_path, after_path, max_items=1)

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["added_items"], 1)
        self.assertEqual(result["added"][0]["id"], "line")
        self.assertEqual(result["truncated"]["added"], 0)

    def test_reports_missing_manifest_as_failed_check(self) -> None:
        result = diff_document_snapshots({}, _manifest([]))

        self.assertFalse(result["ok"])
        self.assertEqual(result["failures"][0]["name"], "before_manifest_present")

    def test_reports_unloadable_before_artifact_as_failed_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.json"

            result = diff_document_snapshots(missing_path, _manifest([]))

        self.assertFalse(result["ok"])
        self.assertEqual(result["failures"][0]["name"], "before_snapshot_loadable")
        self.assertEqual(result["error"]["type"], "FileNotFoundError")

    def test_reports_invalid_after_artifact_as_failed_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            after_path = Path(temp_dir) / "after.json"
            after_path.write_text("{not-json", encoding="utf-8")

            result = diff_document_snapshots(_manifest([]), after_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["failures"][0]["name"], "after_snapshot_loadable")
        self.assertEqual(result["error"]["type"], "JSONDecodeError")

    def test_reports_non_object_json_artifact_as_failed_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            after_path = Path(temp_dir) / "after.json"
            after_path.write_text("[]", encoding="utf-8")

            result = diff_document_snapshots(_manifest([]), after_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["failures"][0]["name"], "after_snapshot_loadable")
        self.assertEqual(result["error"]["type"], "ValueError")

    def test_can_ignore_noisy_nested_paths_and_keys(self) -> None:
        before = _manifest(
            [
                {
                    "id": "solid",
                    "name": "Solid",
                    "source": "items",
                    "properties": {"timestamp": "10:00", "stable": "yes"},
                    "diagnostics": {"session_id": "a", "revision": 1},
                }
            ]
        )
        after = _manifest(
            [
                {
                    "id": "solid",
                    "name": "Solid",
                    "source": "items",
                    "properties": {"timestamp": "10:01", "stable": "yes"},
                    "diagnostics": {"session_id": "b", "revision": 2},
                }
            ]
        )

        noisy = diff_document_snapshots(before, after)
        stable = diff_document_snapshots(
            before,
            after,
            ignore_paths=["properties.timestamp"],
            ignore_keys=["session_id", "revision"],
        )

        self.assertEqual(noisy["summary"]["changed_items"], 1)
        self.assertEqual(stable["summary"]["changed_items"], 0)
        self.assertEqual(stable["ignored"]["paths"], ["properties.timestamp"])
        self.assertEqual(stable["ignored"]["keys"], ["revision", "session_id"])

    def test_default_volatile_ignores_are_opt_in(self) -> None:
        before = _manifest(
            [
                {
                    "id": "solid",
                    "name": "Solid",
                    "source": "items",
                    "timestamp": "10:00",
                    "diagnostics": {"session_id": "a", "stable": "yes"},
                }
            ]
        )
        after = _manifest(
            [
                {
                    "id": "solid",
                    "name": "Solid",
                    "source": "items",
                    "timestamp": "10:01",
                    "diagnostics": {"session_id": "b", "stable": "yes"},
                }
            ]
        )

        noisy = diff_document_snapshots(before, after)
        stable = diff_document_snapshots(before, after, use_default_volatile_ignores=True)

        self.assertEqual(noisy["summary"]["changed_items"], 1)
        self.assertEqual(noisy["ignored"]["default_volatile"], False)
        self.assertEqual(stable["summary"]["changed_items"], 0)
        self.assertTrue(stable["ignored"]["default_volatile"])
        self.assertIn("session_id", stable["ignored"]["keys"])
        self.assertIn("timestamp", stable["ignored"]["keys"])

    def test_duplicate_id_entries_are_not_collapsed(self) -> None:
        before = _manifest(
            [
                {"id": "shared", "name": "tree-node", "source": "tree", "source_index": 0},
                {"id": "shared", "name": "item-row", "source": "items", "source_index": 0},
            ]
        )
        after = _manifest(
            [
                {"id": "shared", "name": "tree-node", "source": "tree", "source_index": 0},
                {"id": "shared", "name": "item-row", "source": "items", "source_index": 0},
                {"id": "shared", "name": "duplicate-row", "source": "items", "source_index": 1},
            ]
        )

        diff = diff_document_snapshots(before, after)

        self.assertEqual(diff["summary"]["before_items"], 2)
        self.assertEqual(diff["summary"]["after_items"], 3)
        self.assertEqual(diff["summary"]["added_items"], 1)
        self.assertEqual(diff["added"][0]["name"], "duplicate-row")


def _manifest(entries: list[dict], *, items: int | None = None) -> dict:
    return {
        "counts": {
            "items": len(entries) if items is None else items,
            "tree_nodes": sum(1 for item in entries if item.get("source") == "tree"),
            "indexed_items": len(entries),
        },
        "item_index": {"entries": entries},
    }


if __name__ == "__main__":
    unittest.main()
