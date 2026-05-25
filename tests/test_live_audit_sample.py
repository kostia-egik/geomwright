import importlib.util
import unittest
from pathlib import Path

from kompas_mcp.tool_catalog import get_mcp_tool_catalog


class LiveAuditSampleTests(unittest.TestCase):
    def test_low_level_catalog_payload_is_accepted_by_audit_sample(self) -> None:
        sample = _load_sample()
        payload = get_mcp_tool_catalog(category="low_level_runtime")

        self.assertTrue(sample._has_catalog_tools(payload))

        preview = sample._preview_payload(payload)
        self.assertEqual(preview["category_count"], 1)
        self.assertGreater(preview["tool_count"], 0)

    def test_step_document_id_is_promoted_to_audit_summary(self) -> None:
        sample = _load_sample()
        audit = {}
        step = {"payload": {"document": {"id": "part-1.m3d", "name": "part-1.m3d"}}}

        sample._record_step_document_id(audit, "opened_document_id", step)

        self.assertEqual(audit["opened_document_id"], "part-1.m3d")

    def test_model_object_probe_preview_keeps_bounded_summary(self) -> None:
        sample = _load_sample()
        payload = {
            "document": {"id": "part-1.m3d"},
            "probe": {
                "summary": {
                    "collection_count": 5,
                    "available_count": 5,
                    "nonempty_count": 1,
                    "total_items": 2,
                },
                "collections": [{"name": "sketches", "preview": [{"name": "Sketch1"}]}],
            },
        }

        preview = sample._preview_payload(payload)

        self.assertEqual(preview["probe_summary"]["total_items"], 2)
        self.assertNotIn("collections", preview)

    def test_readback_probe_preview_does_not_emit_null_probe_summary(self) -> None:
        sample = _load_sample()
        payload = {
            "ok": True,
            "summary": {"items": 1},
            "probe": {"mode": "active_document", "document_id": "part-1.m3d"},
        }

        preview = sample._preview_payload(payload)

        self.assertNotIn("probe_summary", preview)
        self.assertEqual(preview["probe"]["mode"], "active_document")

    def test_write_v2_audit_manifest_keeps_raw_result_bounded(self) -> None:
        sample = _load_write_sample()
        tool_inputs = {"name": "SK", "entities": [{"kind": "segment", "start": [0, 0], "end": [1, 0]}]}
        result = {
            "ok": True,
            "result_preview": {"ok": True, "items": 1},
            "snapshots": {
                "before": {"summary": {"items": 1}},
                "after": {"summary": {"items": 3}},
            },
            "delta": {
                "summary": {"added_items": 2, "removed_items": 0, "changed_items": 0},
                "counts_delta": {"items": {"delta": 2}},
            },
            "parameterization": {
                "ok": True,
                "constraints": {"live_status": "applied", "applied_count": 3, "failed_count": 0, "skipped_count": 0},
                "dimensions": {"live_status": "applied", "applied_count": 2, "failed_count": 0},
                "geometry_checks": {"ok": True, "checked_count": 2, "failed_count": 0},
            },
            "failures": [],
        }

        manifest = sample._build_write_manifest(tool_inputs, result)

        self.assertTrue(manifest["ok"])
        self.assertEqual(manifest["tool_inputs"], tool_inputs)
        self.assertEqual(manifest["before_summary"]["items"], 1)
        self.assertEqual(manifest["after_summary"]["items"], 3)
        self.assertEqual(manifest["delta_summary"]["added_items"], 2)
        self.assertTrue(manifest["parameterization"]["ok"])
        self.assertEqual(manifest["parameterization"]["constraints"]["applied_count"], 3)
        self.assertEqual(manifest["parameterization"]["dimensions"]["applied_count"], 2)
        self.assertNotIn("snapshots", manifest)


def _load_sample():
    root = Path(__file__).resolve().parents[1]
    path = root / "sample" / "audit_live_kompas_low_level_2026_05_20.py"
    spec = importlib.util.spec_from_file_location("audit_live_kompas_low_level_sample", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load sample from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_write_sample():
    root = Path(__file__).resolve().parents[1]
    path = root / "sample" / "audit_live_kompas_write_v2_2026_05_24.py"
    spec = importlib.util.spec_from_file_location("audit_live_kompas_write_v2_sample", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load sample from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
