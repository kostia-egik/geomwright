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


def _load_sample():
    root = Path(__file__).resolve().parents[1]
    path = root / "sample" / "audit_live_kompas_low_level_2026_05_20.py"
    spec = importlib.util.spec_from_file_location("audit_live_kompas_low_level_sample", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load sample from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
