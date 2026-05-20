import unittest

from kompas_mcp.sketch_runtime import (
    DirectionAlias,
    Frame2D,
    Vector2,
    verify_direction_aliases,
)


class SketchRuntimeDirectionAliasTests(unittest.TestCase):
    def test_direction_aliases_report_ok(self) -> None:
        frame = Frame2D("profile_lcs", x_axis=Vector2(1.0, 0.0), y_axis=Vector2(0.0, 1.0))

        report = verify_direction_aliases(
            frame,
            (
                DirectionAlias("axis_forward", Vector2(10.0, 0.0), "+x"),
                DirectionAlias("radial_outward", Vector2(0.0, 2.0), "+y"),
                DirectionAlias("radial_inward", Vector2(0.0, -2.0), "-y"),
            ),
        )

        self.assertTrue(report.ok)
        self.assertEqual(len(report.results), 3)
        self.assertEqual(report.diagnostics, ())
        self.assertEqual(report.to_dict()["stage"], "direction_aliases")

    def test_direction_alias_mismatch_is_diagnostic(self) -> None:
        frame = Frame2D("profile_lcs", x_axis=Vector2(1.0, 0.0), y_axis=Vector2(0.0, 1.0))

        report = verify_direction_aliases(
            frame,
            (DirectionAlias("radial_outward", Vector2(0.0, -1.0), "+y"),),
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "direction_alias_mismatch")

    def test_zero_direction_alias_is_diagnostic(self) -> None:
        frame = Frame2D("profile_lcs", x_axis=Vector2(1.0, 0.0), y_axis=Vector2(0.0, 1.0))

        report = verify_direction_aliases(
            frame,
            (DirectionAlias("bad", Vector2(0.0, 0.0), "+x"),),
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "zero_direction_alias")

    def test_invalid_frame_is_diagnostic(self) -> None:
        frame = Frame2D("bad_lcs", x_axis=Vector2(0.0, 0.0), y_axis=Vector2(0.0, 1.0))

        report = verify_direction_aliases(
            frame,
            (DirectionAlias("axis_forward", Vector2(1.0, 0.0), "+x"),),
        )

        self.assertFalse(report.ok)
        codes = [diagnostic.code for diagnostic in report.diagnostics]
        self.assertIn("zero_x_axis", codes)
        self.assertIn("invalid_direction_alias_frame", codes)


if __name__ == "__main__":
    unittest.main()
