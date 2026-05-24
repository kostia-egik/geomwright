import unittest

from kompas_mcp.document_snapshot_verify import verify_document_snapshot_delta


class DocumentSnapshotDeltaVerificationTests(unittest.TestCase):
    def test_verifies_expected_added_item_and_count_delta(self) -> None:
        before = _manifest([{"id": "root", "source": "tree"}], items=1)
        after = _manifest(
            [
                {"id": "root", "source": "tree"},
                {"id": "line-1", "name": "Line", "type": "line", "source": "items"},
            ],
            items=2,
        )

        result = verify_document_snapshot_delta(
            "create_line",
            before=before,
            after=after,
            expected_added=1,
            require_no_removed=True,
            require_no_changed=True,
            expected_counts_delta={"items": 1, "indexed_items": 1},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["stage"], "snapshot_delta_verification")
        self.assertEqual(result["operation"], "create_line")
        self.assertEqual(result["delta"]["summary"]["added_items"], 1)
        self.assertEqual(result["delta"]["added"][0]["id"], "line-1")

    def test_reports_failed_expected_delta_checks(self) -> None:
        before = _manifest([{"id": "root"}, {"id": "line-1", "source": "items"}], items=2)
        after = _manifest([{"id": "root"}], items=1)

        result = verify_document_snapshot_delta(
            "delete_line_unexpected",
            before=before,
            after=after,
            expected_added=1,
            require_no_removed=True,
            expected_counts_delta={"items": 1},
        )

        failure_names = [item["name"] for item in result["failures"]]
        self.assertFalse(result["ok"])
        self.assertIn("operation_result_ok", failure_names)
        self.assertIn("snapshot_delta_added_items", failure_names)
        self.assertIn("snapshot_delta_no_removed", failure_names)
        self.assertIn("snapshot_count_delta:items", failure_names)
        self.assertEqual(result["delta"]["summary"]["removed_items"], 1)

    def test_accepts_existing_diff_payload(self) -> None:
        diff = {
            "ok": True,
            "summary": {"added_items": 2, "removed_items": 0, "changed_items": 0},
            "counts_delta": {"items": {"before": 3, "after": 5, "delta": 2}},
            "added": [{"id": "a"}, {"id": "b"}],
            "removed": [],
            "changed": [],
            "truncated": {"added": 0, "removed": 0, "changed": 0},
        }

        result = verify_document_snapshot_delta(
            "create_two_objects",
            diff=diff,
            min_added=1,
            max_added=2,
            require_no_removed=True,
            expected_counts_delta={"items": 2},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["delta"]["summary"]["added_items"], 2)

    def test_can_ignore_noisy_fields_when_building_delta(self) -> None:
        before = _manifest(
            [
                {
                    "id": "root",
                    "source": "tree",
                    "properties": {"timestamp": "10:00"},
                    "diagnostics": {"session_id": "a"},
                }
            ]
        )
        after = _manifest(
            [
                {
                    "id": "root",
                    "source": "tree",
                    "properties": {"timestamp": "10:01"},
                    "diagnostics": {"session_id": "b"},
                }
            ]
        )

        result = verify_document_snapshot_delta(
            "stability",
            before=before,
            after=after,
            expected_changed=0,
            ignore_paths=["properties.timestamp"],
            ignore_keys=["session_id"],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["delta"]["summary"]["changed_items"], 0)
        self.assertEqual(result["delta"]["ignored"]["paths"], ["properties.timestamp"])

    def test_can_use_default_volatile_ignores_when_building_delta(self) -> None:
        before = _manifest([{"id": "root", "source": "tree", "timestamp": "10:00", "session_id": "a"}])
        after = _manifest([{"id": "root", "source": "tree", "timestamp": "10:01", "session_id": "b"}])

        result = verify_document_snapshot_delta(
            "stability",
            before=before,
            after=after,
            expected_changed=0,
            use_default_volatile_ignores=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["delta"]["summary"]["changed_items"], 0)
        self.assertTrue(result["delta"]["ignored"]["default_volatile"])

    def test_requires_diff_or_before_after(self) -> None:
        result = verify_document_snapshot_delta("missing_inputs", expected_added=1)

        self.assertFalse(result["ok"])
        self.assertEqual(result["failures"][0]["name"], "operation_result_ok")
        self.assertIn("snapshot_delta_input_present", [item["name"] for item in result["failures"]])

    def test_rejects_non_object_diff_payload(self) -> None:
        result = verify_document_snapshot_delta("bad_diff", diff=[])  # type: ignore[arg-type]

        self.assertFalse(result["ok"])
        self.assertIn("snapshot_delta_payload_object", [item["name"] for item in result["failures"]])


def _manifest(entries: list[dict], *, items: int | None = None) -> dict:
    return {
        "counts": {
            "items": len(entries) if items is None else items,
            "indexed_items": len(entries),
            "tree_nodes": sum(1 for item in entries if item.get("source") == "tree"),
        },
        "item_index": {"entries": entries},
    }


if __name__ == "__main__":
    unittest.main()
