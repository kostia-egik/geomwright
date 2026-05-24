import unittest

from kompas_mcp.operation_snapshot_loop import execute_snapshot_verified_operation


class SnapshotVerifiedOperationTests(unittest.TestCase):
    def test_runs_operation_between_snapshots_and_verifies_delta(self) -> None:
        calls: list[str] = []

        result = execute_snapshot_verified_operation(
            "create_line",
            lambda: calls.append("operation") or {"ok": True, "id": "line-1", "type": "line"},
            before_snapshot=lambda: calls.append("before") or _manifest_snapshot([{"id": "root"}], items=1),
            after_snapshot=lambda: calls.append("after")
            or _manifest_snapshot([{"id": "root"}, {"id": "line-1", "type": "line", "source": "items"}], items=2),
            expected_added=1,
            require_no_removed=True,
            require_no_changed=True,
            expected_counts_delta={"items": 1, "indexed_items": 1},
        )

        self.assertEqual(calls, ["before", "operation", "after"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["execution"]["delta_verification_ran"])
        self.assertEqual(result["result_preview"]["id"], "line-1")
        self.assertEqual(result["delta"]["summary"]["added_items"], 1)
        self.assertEqual(result["snapshots"]["after"]["counts"]["items"], 2)

    def test_skips_operation_after_failed_before_snapshot(self) -> None:
        calls: list[str] = []

        result = execute_snapshot_verified_operation(
            "create_line",
            lambda: calls.append("operation") or {"ok": True},
            before_snapshot={"ok": False, "summary": {"reason": "no active document"}},
            after_snapshot=lambda: calls.append("after") or _manifest_snapshot([]),
        )

        self.assertEqual(calls, [])
        self.assertFalse(result["ok"])
        self.assertFalse(result["execution"]["operation_ran"])
        self.assertFalse(result["execution"]["after_snapshot_ran"])
        self.assertIn("operation_skipped_after_before_snapshot", [item["name"] for item in result["failures"]])

    def test_classifies_operation_exception_without_after_snapshot(self) -> None:
        calls: list[str] = []

        def run_operation() -> dict:
            calls.append("operation")
            raise RuntimeError("COM call failed while creating line")

        result = execute_snapshot_verified_operation(
            "create_line",
            run_operation,
            before_snapshot=lambda: calls.append("before") or _manifest_snapshot([{"id": "root"}]),
            after_snapshot=lambda: calls.append("after") or _manifest_snapshot([]),
        )

        self.assertEqual(calls, ["before", "operation"])
        self.assertFalse(result["ok"])
        self.assertFalse(result["execution"]["after_snapshot_ran"])
        self.assertEqual(result["error"]["code"], "COM_CALL_FAILED")

    def test_reports_failed_snapshot_delta_verification(self) -> None:
        result = execute_snapshot_verified_operation(
            "create_line",
            lambda: {"ok": True, "id": "line-1"},
            before_snapshot=_manifest_snapshot([{"id": "root"}, {"id": "line-1"}], items=2),
            after_snapshot=_manifest_snapshot([{"id": "root"}], items=1),
            expected_added=1,
            require_no_removed=True,
        )

        failure_names = [item["name"] for item in result["failures"]]
        self.assertFalse(result["ok"])
        self.assertIn("snapshot_delta_verification_ok", failure_names)
        self.assertIn("snapshot_delta:snapshot_delta_added_items", failure_names)
        self.assertIn("snapshot_delta:snapshot_delta_no_removed", failure_names)
        self.assertEqual(result["delta"]["summary"]["removed_items"], 1)

    def test_passes_noise_filters_to_delta_verification(self) -> None:
        result = execute_snapshot_verified_operation(
            "rename_metadata",
            lambda: {"ok": True},
            before_snapshot=_manifest_snapshot(
                [{"id": "root", "timestamp": "before", "properties": {"session": "a"}}],
                items=1,
            ),
            after_snapshot=_manifest_snapshot(
                [{"id": "root", "timestamp": "after", "properties": {"session": "b"}}],
                items=1,
            ),
            expected_changed=0,
            ignore_paths=["properties.session"],
            use_default_volatile_ignores=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["delta"]["summary"]["changed_items"], 0)
        self.assertTrue(result["delta"]["ignored"]["default_volatile"])
        self.assertIn("properties.session", result["delta"]["ignored"]["paths"])

    def test_reports_non_object_snapshot_payload_as_failure(self) -> None:
        result = execute_snapshot_verified_operation(
            "create_line",
            lambda: {"ok": True},
            before_snapshot=lambda: [],
            after_snapshot=lambda: _manifest_snapshot([]),
        )

        self.assertFalse(result["ok"])
        self.assertFalse(result["execution"]["before_snapshot_ran"])
        self.assertFalse(result["execution"]["operation_ran"])
        self.assertEqual(result["error"]["exception_type"], "TypeError")
        self.assertIn("snapshot payload must be dict", result["error"]["message"])


def _manifest_snapshot(entries: list[dict], *, items: int | None = None) -> dict:
    return {
        "ok": True,
        "snapshot": {
            "summary": {"items": len(entries) if items is None else items},
            "counts": {
                "items": len(entries) if items is None else items,
                "indexed_items": len(entries),
            },
            "manifest": {
                "counts": {
                    "items": len(entries) if items is None else items,
                    "indexed_items": len(entries),
                },
                "item_index": {"entries": entries},
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
