import tempfile
import unittest
from struct import pack
import zlib
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from kompas_mcp.formula_probe import inspect_m3d_formula_contents, probe_model_formulas


class FormulaProbeTests(unittest.TestCase):
    def test_inspect_m3d_formula_contents_extracts_public_variables_and_formulas(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            model = Path(temp_dir) / "spring.m3d"
            _write_test_model(
                model,
                [
                    _bootstrap_record("SPG_EXT01_D1", 34.0),
                    _bootstrap_record("SPG_EXT01_WD1", 4.0),
                    _bootstrap_record("v77", 8.727272727272727),
                    _bootstrap_record("v762", 270.0),
                    "Compression spring outer diameter demo [SPG_EXT01] | spring | Outer coil diameter SPG_EXT01_D1",
                    "Compression spring outer diameter demo [SPG_EXT01] | spring | Wire diameter SPG_EXT01_WD1",
                    "v77\x03\x00Шаг",
                    "v762\x08\x00Вращение",
                    "((SPG_EXT01_D1) - (SPG_EXT01_WD1)) / 2",
                    "(SPG_EXT01_WD1) / 2",
                    "v762+(360*(v80/v77))",
                ],
            )

            report = inspect_m3d_formula_contents(model)

            self.assertTrue(report["ok"])
            self.assertEqual(report["public_variables"][0]["name"], "SPG_EXT01_D1")
            self.assertEqual(report["public_variables"][1]["name"], "SPG_EXT01_WD1")
            self.assertEqual(report["public_variables"][0]["value"], 34.0)
            self.assertEqual(report["public_variables"][1]["value"], 4.0)
            self.assertEqual(report["internal_variables"][0]["name"], "v77")
            self.assertEqual(report["internal_variables"][0]["label"], "Шаг")
            self.assertEqual(report["internal_variables"][0]["role"], "pitch")
            self.assertAlmostEqual(report["internal_variables"][0]["value"], 8.727272727272727)
            expressions = [item["expression"] for item in report["formula_strings"]]
            self.assertIn("((SPG_EXT01_D1) - (SPG_EXT01_WD1)) / 2", expressions)
            self.assertIn("(SPG_EXT01_WD1) / 2", expressions)
            internal = next(item for item in report["formula_strings"] if item["scope"] == "internal")
            self.assertEqual(internal["references"], ["v762", "v80", "v77"])
            self.assertEqual(internal["interpreted_expression"], "rotation+(360*(v80/pitch))")
            named = next(item for item in report["formula_strings"] if item["expression"] == "(SPG_EXT01_WD1) / 2")
            self.assertEqual(named["evaluated_value"], 2.0)

    def test_probe_model_formulas_combines_com_and_contents_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            model = Path(temp_dir) / "spring.m3d"
            output = Path(temp_dir) / "formula_probe.json"
            _write_test_model(
                model,
                [
                    _bootstrap_record("SPG_EXT01_H1", 54.0),
                    _bootstrap_record("SPG_EXT01_N21", 0.75),
                    _bootstrap_record("SPG_EXT01_WD1", 4.0),
                    "Compression spring outer diameter demo [SPG_EXT01] | spring | Outer coil diameter SPG_EXT01_D1",
                    "Compression spring outer diameter demo [SPG_EXT01] | spring | Wire diameter SPG_EXT01_WD1",
                    "v77\x03\x00Шаг",
                    "SPG_EXT01_H1 - 2 * (SPG_EXT01_N21 * SPG_EXT01_WD1)",
                    "v762+(360*(v80/v77))",
                ],
            )
            adapter = _FakeFormulaProbeAdapter()

            report = probe_model_formulas(adapter, model_path=str(model), output_path=output)

            self.assertTrue(report["ok"])
            self.assertTrue(output.exists())
            self.assertEqual(report["summary"]["sketch_count"], 1)
            self.assertEqual(report["summary"]["feature_count"], 1)
            self.assertEqual(report["summary"]["dimension_formula_count"], 2)
            self.assertEqual(report["summary"]["constraint_formula_count"], 1)
            self.assertEqual(report["summary"]["feature_variable_formula_count"], 1)
            self.assertIn("contents", report)
            self.assertEqual(
                adapter.calls,
                ["open", "tree:doc-1", "sketches:doc-1", "features:doc-1", "dims:101", "cons:101", "inspect:evolution:0", "close"],
            )

    def test_probe_stops_after_open_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            model = Path(temp_dir) / "spring.m3d"
            _write_test_model(model, ["SPG_EXT01_H1 - SPG_EXT01_WD1"])
            adapter = _FailingOpenAdapter()

            report = probe_model_formulas(adapter, model_path=str(model))

        self.assertFalse(report["ok"])
        self.assertEqual(report["failures"][0]["name"], "open_document")
        self.assertEqual(adapter.calls, ["open"])


class _FakeFormulaProbeAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.document = {"id": "doc-1", "name": "spring.m3d", "path": "spring.m3d"}

    def open_document(self, path: str, *, visible: bool, read_only: bool) -> dict[str, Any]:
        self.calls.append("open")
        return {"document": self.document, "visible": visible, "read_only": read_only}

    def close_document(self, *, document_id: str, save: bool) -> dict[str, Any]:
        self.calls.append("close")
        return {"document": self.document, "closed": True, "save": save}

    def get_document_tree(self, document_id: str | None = None) -> dict[str, Any]:
        self.calls.append(f"tree:{document_id}")
        return {"document": self.document, "tree": {"id": "root", "name": "Part", "children": []}}

    def list_sketches(self, document_id: str | None = None, max_items: int | None = None) -> dict[str, Any]:
        self.calls.append(f"sketches:{document_id}")
        return {"items": [{"reference": 101, "name": "spring_wire_profile", "index": 0}]}

    def list_sketch_dimensions(
        self,
        document_id: str | None = None,
        sketch_ref: str | int | None = None,
        kinds: list[str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(f"dims:{sketch_ref}")
        return {
            "items": [
                {"index": 0, "kind": "line_length", "reference": 201, "expression": "((SPG_EXT01_D1) - (SPG_EXT01_WD1)) / 2"},
                {"index": 1, "kind": "line_length", "reference": 202, "expression": "(SPG_EXT01_WD1) / 2"},
            ]
        }
    def list_sketch_constraints(
        self,
        document_id: str | None = None,
        sketch_ref: str | int | None = None,
        kinds: list[str] | None = None,
        max_items: int | None = None,
    ) -> dict[str, Any]:
        self.calls.append(f"cons:{sketch_ref}")
        return {
            "items": [
                {"index": 0, "kind": "fixed_length", "reference": 301, "expression": "SPG_EXT01_N21 * SPG_EXT01_WD1"},
            ]
        }

    def list_features(
        self,
        document_id: str | None = None,
        kinds: list[str] | None = None,
        max_items: int | None = None,
    ) -> dict[str, Any]:
        self.calls.append(f"features:{document_id}")
        return {"items": [{"kind": "evolution", "index": 0, "reference": 401, "name": "spring_body"}]}

    def inspect_feature(
        self,
        document_id: str | None = None,
        feature: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(f"inspect:{feature.get('kind')}:{feature.get('index')}")
        return {
            "item": {
                "kind": "evolution",
                "index": 0,
                "reference": 401,
                "name": "spring_body",
                "variables": [
                    {"index": 0, "name": "angle_step", "expression": "v762+(360*(v80/v77))"},
                ],
            }
        }


class _FailingOpenAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def open_document(self, path: str, *, visible: bool, read_only: bool) -> dict[str, Any]:
        self.calls.append("open")
        return {"ok": False, "error": "document is locked"}


def _write_test_model(path: Path, chunks: list[str | bytes]) -> None:
    payload = bytearray()
    for chunk in chunks:
        if isinstance(chunk, bytes):
            payload.extend(zlib.compress(chunk))
        else:
            payload.extend(zlib.compress(chunk.encode("utf-16le")))
    contents = b"KF" + bytes(payload)
    with ZipFile(path, "w") as archive:
        archive.writestr("Contents", contents)


def _bootstrap_record(name: str, value: float) -> bytes:
    return (
        b"\x00" * 16
        + name.encode("utf-16le")
        + b"\x02\x80\x37\x29\x01\x00\x00"
        + pack("<d", value)
    )


if __name__ == "__main__":
    unittest.main()
