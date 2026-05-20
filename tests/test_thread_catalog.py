import sqlite3
import tempfile
import unittest
from pathlib import Path

from kompas_mcp.metric_thread_geometry import build_metric_thread_geometry
from kompas_mcp.thread_catalog import assess_thread_standard_for_helical_thread_v1
from kompas_mcp.thread_catalog import list_thread_catalog_standards
from kompas_mcp.thread_catalog import list_helical_thread_v1_candidates
from kompas_mcp.thread_catalog import list_thread_standard_entries
from kompas_mcp.thread_catalog import resolve_thread_designation_entry
from kompas_mcp.thread_catalog import resolve_thread_standard_entry


class ThreadCatalogTests(unittest.TestCase):
    def _create_catalog_fixture(self) -> str:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        database_path = Path(temp_dir.name) / "thread.db"
        connection = sqlite3.connect(str(database_path))
        try:
            cursor = connection.cursor()
            cursor.execute(
                "create table [description] (n integer, displayname text, koeff real, cone real, tablename text primary key, note integer)"
            )
            cursor.execute(
                "insert into [description] values (?, ?, ?, ?, ?, ?)",
                (1, "Custom metric coarse", 1.08, 0.0, "custom_metric", 0),
            )
            cursor.execute(
                "insert into [description] values (?, ?, ?, ?, ?, ?)",
                (2, "Custom metric fine", 1.08, 0.0, "custom_metric_fine", 0),
            )
            cursor.execute(
                "insert into [description] values (?, ?, ?, ?, ?, ?)",
                (3, "Pipe thread Whitworth ISO 228", 1.28, 0.0, "custom_whitworth", 1),
            )
            cursor.execute(
                "insert into [description] values (?, ?, ?, ?, ?, ?)",
                (4, "Custom metric conical", 1.08, 3.58, "custom_metric_conical", 1),
            )
            cursor.execute("create table [custom_metric] (d real, p real, d1 real, title text)")
            cursor.execute("create table [custom_metric_fine] (d real, p real, d1 real, title text)")
            cursor.execute("create table [custom_whitworth] (d real, p real, d1 real, title text)")
            cursor.execute("create table [custom_metric_conical] (d real, p real, d1 real, title text)")
            cursor.execute(
                "insert into [custom_metric] values (?, ?, ?, ?)",
                (20.0, 2.5, 17.29367, "M20x2.5"),
            )
            cursor.execute(
                "insert into [custom_metric_fine] values (?, ?, ?, ?)",
                (20.0, 2.0, 17.83494, "M20x2.0"),
            )
            cursor.execute(
                "insert into [custom_whitworth] values (?, ?, ?, ?)",
                (20.0, 2.5, 17.0, "G3/4"),
            )
            cursor.execute(
                "insert into [custom_metric_conical] values (?, ?, ?, ?)",
                (20.0, 2.5, 17.29367, "M20x2.5 conical"),
            )
            connection.commit()
        finally:
            connection.close()
        return str(database_path)

    def test_assess_thread_standard_metric_cylindrical_is_compatible(self) -> None:
        assessment = assess_thread_standard_for_helical_thread_v1(
            {"table_name": "custom_metric", "display_name": "Custom metric coarse", "conical_thread_angle": 0.0}
        )
        self.assertTrue(assessment["compatible"])
        self.assertEqual(assessment["profile_family"], "metric_v60")
        self.assertEqual(assessment["suggested_profile_angle_degrees"], 60.0)

    def test_assess_thread_standard_conical_is_incompatible(self) -> None:
        assessment = assess_thread_standard_for_helical_thread_v1(
            {"table_name": "custom_metric_conical", "display_name": "Custom metric conical", "conical_thread_angle": 3.58}
        )
        self.assertFalse(assessment["compatible"])
        self.assertEqual(assessment["profile_family"], "conical")

    def test_assess_thread_standard_unified_inch_is_compatible(self) -> None:
        assessment = assess_thread_standard_for_helical_thread_v1(
            {"table_name": "custom_unc", "display_name": "Unified inch UNC", "conical_thread_angle": 0.0}
        )
        self.assertTrue(assessment["compatible"])
        self.assertEqual(assessment["profile_family"], "unified_un_v60")
        self.assertEqual(assessment["suggested_profile_angle_degrees"], 60.0)

    def test_list_thread_catalog_standards_adds_assessment_fields(self) -> None:
        database_path = self._create_catalog_fixture()
        payload = list_thread_catalog_standards(database_path=database_path)
        self.assertTrue(payload["catalog_found"])
        self.assertEqual(payload["database_path"], database_path)
        standards = {item["table_name"]: item for item in payload["standards"]}
        self.assertIn("custom_metric", standards)
        self.assertIn("custom_whitworth", standards)
        self.assertIn("custom_metric_conical", standards)
        self.assertTrue(standards["custom_metric"]["helical_thread_v1_compatible"])
        self.assertFalse(standards["custom_whitworth"]["helical_thread_v1_compatible"])
        self.assertFalse(standards["custom_metric_conical"]["helical_thread_v1_compatible"])
        self.assertEqual(standards["custom_metric"]["entry_count"], 1)
        self.assertAlmostEqual(standards["custom_metric"]["diameter_min"], 20.0)
        self.assertAlmostEqual(standards["custom_metric"]["diameter_max"], 20.0)
        self.assertAlmostEqual(standards["custom_metric"]["pitch_min"], 2.5)
        self.assertAlmostEqual(standards["custom_metric"]["pitch_max"], 2.5)
        self.assertEqual(standards["custom_metric"]["sample_designations"], ["M20x2.5"])

    def test_list_thread_standard_entries_returns_rows(self) -> None:
        database_path = self._create_catalog_fixture()
        payload = list_thread_standard_entries("custom_metric", database_path=database_path, limit=10)
        self.assertTrue(payload["catalog_found"])
        self.assertEqual(payload["table_name"], "custom_metric")
        self.assertEqual(payload["limit"], 10)
        self.assertEqual(payload["offset"], 0)
        self.assertFalse(payload["has_more"])
        self.assertEqual(len(payload["entries"]), 1)
        entry = payload["entries"][0]
        self.assertEqual(entry["designation"], "M20x2.5")
        self.assertAlmostEqual(entry["d"], 20.0)
        self.assertAlmostEqual(entry["p"], 2.5)
        self.assertAlmostEqual(entry["d1"], 17.29367)
        self.assertAlmostEqual(entry["internal_thread_depth"], (20.0 - 17.29367) / 2.0)
        geometry = build_metric_thread_geometry(20.0, 2.5)
        self.assertAlmostEqual(entry["d1_minor"], geometry["internal_minor_diameter"], places=6)
        self.assertAlmostEqual(entry["d2_pitch"], geometry["pitch_diameter"], places=6)
        self.assertAlmostEqual(entry["d3_external_minor"], geometry["external_minor_diameter"], places=6)

    def test_list_thread_standard_entries_supports_ranges(self) -> None:
        database_path = self._create_catalog_fixture()
        payload = list_thread_standard_entries(
            "custom_metric_fine",
            database_path=database_path,
            diameter_min=19.5,
            diameter_max=20.5,
            pitch_min=1.9,
            pitch_max=2.1,
        )
        self.assertEqual(len(payload["entries"]), 1)
        self.assertEqual(payload["entries"][0]["designation"], "M20x2.0")

    def test_list_helical_thread_v1_candidates_filters_metric_standards(self) -> None:
        database_path = self._create_catalog_fixture()
        payload = list_helical_thread_v1_candidates(database_path=database_path, limit_per_standard=5)
        table_names = {item["table_name"] for item in payload["standards"]}
        self.assertEqual(table_names, {"custom_metric", "custom_metric_fine"})
        standards = {item["table_name"]: item for item in payload["standards"]}
        self.assertEqual(standards["custom_metric"]["entries"][0]["designation"], "M20x2.5")
        self.assertEqual(standards["custom_metric_fine"]["entries"][0]["designation"], "M20x2.0")

    def test_resolve_thread_designation_entry_finds_match(self) -> None:
        database_path = self._create_catalog_fixture()
        payload = resolve_thread_designation_entry("M20x2.5", database_path=database_path)
        self.assertTrue(payload["catalog_found"])
        self.assertEqual(payload["designation"], "M20x2.5")
        matches = payload["matches"]
        self.assertTrue(matches)
        self.assertEqual(matches[0]["table_name"], "custom_metric")
        self.assertAlmostEqual(matches[0]["d"], 20.0)
        self.assertAlmostEqual(matches[0]["p"], 2.5)

    def test_resolve_thread_designation_entry_defaults_to_one_standard(self) -> None:
        database_path = self._create_catalog_fixture()
        payload = resolve_thread_designation_entry("M20x2.0", database_path=database_path)
        self.assertTrue(payload["catalog_found"])
        self.assertEqual(payload["designation"], "M20x2.0")
        self.assertEqual(payload["matches"], [])

        payload = resolve_thread_designation_entry(
            "M20x2.0",
            database_path=database_path,
            standard="custom_metric_fine",
        )
        self.assertTrue(payload["matches"])
        self.assertEqual(payload["matches"][0]["table_name"], "custom_metric_fine")

    def test_resolve_thread_standard_entry_uses_exact_row(self) -> None:
        database_path = self._create_catalog_fixture()
        payload = resolve_thread_standard_entry("custom_metric", 20.0, 2.5, database_path=database_path)
        self.assertTrue(payload["entry_found"])
        self.assertEqual(payload["designation"], "M20x2.5")
        self.assertAlmostEqual(payload["entry"]["d"], 20.0)
        self.assertAlmostEqual(payload["entry"]["p"], 2.5)
        geometry = build_metric_thread_geometry(20.0, 2.5)
        self.assertAlmostEqual(payload["entry"]["d1_minor"], geometry["internal_minor_diameter"], places=6)
        self.assertAlmostEqual(payload["entry"]["d2_pitch"], geometry["pitch_diameter"], places=6)


if __name__ == "__main__":
    unittest.main()
