import unittest

from kompas_mcp.thread_profile_geometry import INCH_TO_MM
from kompas_mcp.thread_profile_geometry import build_pipe_bsp_parallel_thread_geometry
from kompas_mcp.thread_profile_geometry import build_pipe_straight_thread_geometry
from kompas_mcp.thread_profile_geometry import build_pipe_tapered_thread_geometry
from kompas_mcp.thread_profile_geometry import build_unified_inch_thread_geometry
from kompas_mcp.thread_profile_geometry import parse_pipe_bsp_parallel_thread_designation
from kompas_mcp.thread_profile_geometry import parse_pipe_straight_thread_designation
from kompas_mcp.thread_profile_geometry import parse_pipe_tapered_thread_designation
from kompas_mcp.thread_profile_geometry import parse_unified_inch_thread_designation
from kompas_mcp.thread_profile_geometry import resolve_thread_profile_geometry


class ThreadProfileGeometryTests(unittest.TestCase):
    def test_parse_unified_fraction_designation(self) -> None:
        parsed = parse_unified_inch_thread_designation("1/4-20 UNC")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["thread_series"], "UNC")
        self.assertEqual(parsed["profile_family"], "unified_un_v60")
        self.assertAlmostEqual(parsed["major_diameter_inch"], 0.25)
        self.assertAlmostEqual(parsed["tpi"], 20.0)

    def test_parse_unified_number_designation(self) -> None:
        parsed = parse_unified_inch_thread_designation("#10-32 UNF")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["thread_series"], "UNF")
        self.assertAlmostEqual(parsed["major_diameter_inch"], 0.190)
        self.assertAlmostEqual(parsed["tpi"], 32.0)

    def test_resolve_unified_designation_converts_to_mm(self) -> None:
        resolved = resolve_thread_profile_geometry({"designation": "1/4-20 UNC"})
        geometry = resolved["geometry"]
        self.assertEqual(resolved["profile_family"], "unified_un_v60")
        self.assertEqual(resolved["source_units"], "inch")
        self.assertAlmostEqual(geometry["major_diameter"], 0.25 * INCH_TO_MM)
        self.assertAlmostEqual(geometry["pitch"], INCH_TO_MM / 20.0)
        self.assertAlmostEqual(geometry["profile_angle_degrees"], 60.0)

    def test_resolve_unified_explicit_inch_inputs(self) -> None:
        resolved = resolve_thread_profile_geometry(
            {
                "thread_profile_family": "unified_inch_v60",
                "major_diameter_inch": 0.375,
                "tpi": 16,
                "thread_series": "UNC",
            }
        )
        geometry = resolved["geometry"]
        self.assertEqual(geometry["thread_series"], "UNC")
        self.assertAlmostEqual(geometry["major_diameter"], 0.375 * INCH_TO_MM)
        self.assertAlmostEqual(geometry["pitch"], INCH_TO_MM / 16.0)

    def test_build_unified_geometry_uses_v60_basic_coefficients(self) -> None:
        geometry = build_unified_inch_thread_geometry(
            major_diameter_inch=0.25,
            tpi=20,
            thread_series="UNC",
            designation="1/4-20 UNC",
        )
        self.assertAlmostEqual(geometry["major_diameter"], 6.35)
        self.assertAlmostEqual(geometry["pitch"], 1.27)
        self.assertLess(geometry["external_minor_diameter"], geometry["pitch_diameter"])
        self.assertLess(geometry["internal_minor_diameter"], geometry["pitch_diameter"])

    def test_parse_pipe_straight_designation_uses_pipe_table(self) -> None:
        parsed = parse_pipe_straight_thread_designation("1/4 NPS")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["thread_series"], "NPS")
        self.assertEqual(parsed["profile_family"], "pipe_nps_v60")
        self.assertEqual(parsed["nominal_pipe_size"], "1/4")
        self.assertAlmostEqual(parsed["major_diameter_inch"], 0.540)
        self.assertAlmostEqual(parsed["tpi"], 18.0)

    def test_build_pipe_straight_geometry_uses_flat_v60_profile(self) -> None:
        geometry = build_pipe_straight_thread_geometry(nominal_pipe_size="1/4", thread_series="NPS")
        pitch = INCH_TO_MM / 18.0
        self.assertEqual(geometry["profile_family"], "pipe_nps_v60")
        self.assertEqual(geometry["profile_root_shape"], "flat")
        self.assertEqual(geometry["root_radius_policy"], "pipe_flat_truncation")
        self.assertAlmostEqual(geometry["major_diameter"], 0.540 * INCH_TO_MM)
        self.assertAlmostEqual(geometry["pitch"], pitch)
        self.assertAlmostEqual(geometry["external_thread_depth"], 0.8 * pitch)
        self.assertAlmostEqual(geometry["pitch_diameter"], geometry["major_diameter"] - 0.8 * pitch)
        self.assertGreater(geometry["root_flat_width"], 0.0)

    def test_resolve_pipe_designation_converts_to_mm(self) -> None:
        resolved = resolve_thread_profile_geometry({"designation": "1/4-18 NPSM"})
        geometry = resolved["geometry"]
        self.assertEqual(resolved["profile_family"], "pipe_nps_v60")
        self.assertEqual(resolved["thread_series"], "NPSM")
        self.assertEqual(resolved["source_units"], "inch")
        self.assertEqual(resolved["resolved_from"], "pipe_designation")
        self.assertAlmostEqual(geometry["major_diameter"], 0.540 * INCH_TO_MM)
        self.assertAlmostEqual(geometry["pitch"], INCH_TO_MM / 18.0)

    def test_parse_pipe_tapered_designation_uses_pipe_table(self) -> None:
        parsed = parse_pipe_tapered_thread_designation("1/4 NPT")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["thread_series"], "NPT")
        self.assertEqual(parsed["profile_family"], "pipe_npt_v60")
        self.assertEqual(parsed["nominal_pipe_size"], "1/4")
        self.assertAlmostEqual(parsed["major_diameter_inch"], 0.540)
        self.assertAlmostEqual(parsed["tpi"], 18.0)

    def test_build_pipe_tapered_geometry_marks_conical_carrier(self) -> None:
        geometry = build_pipe_tapered_thread_geometry(nominal_pipe_size="1/4")
        self.assertEqual(geometry["profile_family"], "pipe_npt_v60")
        self.assertEqual(geometry["thread_series"], "NPT")
        self.assertEqual(geometry["profile_root_shape"], "flat")
        self.assertEqual(geometry["carrier_shape"], "conical")
        self.assertEqual(geometry["taper_direction"], "inward")
        self.assertAlmostEqual(geometry["taper_diameter_ratio"], 1.0 / 16.0)
        self.assertAlmostEqual(geometry["taper_radius_ratio"], 1.0 / 32.0)

    def test_resolve_pipe_tapered_designation_converts_to_mm(self) -> None:
        resolved = resolve_thread_profile_geometry({"designation": "1/4-18 NPT"})
        geometry = resolved["geometry"]
        self.assertEqual(resolved["profile_family"], "pipe_npt_v60")
        self.assertEqual(resolved["thread_series"], "NPT")
        self.assertEqual(resolved["source_units"], "inch")
        self.assertEqual(resolved["resolved_from"], "pipe_tapered_designation")
        self.assertAlmostEqual(geometry["major_diameter"], 0.540 * INCH_TO_MM)
        self.assertAlmostEqual(geometry["pitch"], INCH_TO_MM / 18.0)
        self.assertEqual(geometry["carrier_shape"], "conical")

    def test_parse_pipe_bsp_parallel_designation_uses_pipe_table(self) -> None:
        parsed = parse_pipe_bsp_parallel_thread_designation("G 1/4")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["thread_series"], "G")
        self.assertEqual(parsed["profile_family"], "pipe_bsp_g_v55")
        self.assertEqual(parsed["nominal_pipe_size"], "1/4")
        self.assertAlmostEqual(parsed["major_diameter_inch"], 13.157 / INCH_TO_MM, places=6)
        self.assertAlmostEqual(parsed["tpi"], 19.0)

    def test_build_pipe_bsp_parallel_geometry_uses_whitworth_profile(self) -> None:
        geometry = build_pipe_bsp_parallel_thread_geometry(nominal_pipe_size="1/4")
        pitch = INCH_TO_MM / 19.0
        self.assertEqual(geometry["profile_family"], "pipe_bsp_g_v55")
        self.assertEqual(geometry["thread_series"], "G")
        self.assertEqual(geometry["profile_root_shape"], "round")
        self.assertEqual(geometry["root_radius_policy"], "whitworth_equal_rounding")
        self.assertAlmostEqual(geometry["major_diameter"], 13.157, places=3)
        self.assertAlmostEqual(geometry["pitch"], pitch, places=6)
        self.assertAlmostEqual(geometry["profile_angle_degrees"], 55.0, places=6)
        self.assertAlmostEqual(geometry["external_thread_depth"], 0.640327 * pitch, places=5)
        self.assertAlmostEqual(geometry["internal_thread_depth"], 0.640327 * pitch, places=5)
        self.assertAlmostEqual(geometry["crest_round_radius"], 0.137329 * pitch, places=5)
        self.assertAlmostEqual(geometry["root_round_radius"], 0.137329 * pitch, places=5)
        self.assertLess(geometry["external_minor_diameter"], geometry["pitch_diameter"])

    def test_resolve_pipe_bsp_parallel_designation_converts_to_mm(self) -> None:
        resolved = resolve_thread_profile_geometry({"designation": "G 1/4"})
        geometry = resolved["geometry"]
        self.assertEqual(resolved["profile_family"], "pipe_bsp_g_v55")
        self.assertEqual(resolved["thread_series"], "G")
        self.assertEqual(resolved["source_units"], "inch")
        self.assertEqual(resolved["resolved_from"], "pipe_bsp_designation")
        self.assertAlmostEqual(geometry["major_diameter"], 13.157, places=3)
        self.assertAlmostEqual(geometry["pitch"], INCH_TO_MM / 19.0, places=6)
        self.assertAlmostEqual(geometry["profile_angle_degrees"], 55.0, places=6)


if __name__ == "__main__":
    unittest.main()
