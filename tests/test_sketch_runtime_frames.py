import unittest

from kompas_mcp.sketch_runtime import Frame2D, Vector2, verify_frame


class SketchRuntimeFrameTests(unittest.TestCase):
    def test_right_handed_frame_reports_ok(self) -> None:
        frame = Frame2D(
            id="profile_lcs",
            x_axis=Vector2(1.0, 0.0),
            y_axis=Vector2(0.0, 1.0),
            x_role="along_axis",
            y_role="radial_outward",
        )

        report = verify_frame(frame, stage="before_sketch")

        self.assertTrue(report.ok)
        self.assertEqual(report.handedness, "right")
        self.assertEqual(report.to_dict()["stage"], "before_sketch")

    def test_inverted_y_axis_reports_wrong_handedness(self) -> None:
        frame = Frame2D(
            id="profile_lcs",
            x_axis=Vector2(1.0, 0.0),
            y_axis=Vector2(0.0, -1.0),
            x_role="along_axis",
            y_role="radial_outward",
        )

        report = verify_frame(frame)

        self.assertFalse(report.ok)
        self.assertEqual(report.handedness, "left")
        self.assertEqual(report.diagnostics[0].code, "wrong_handedness")
        self.assertEqual(report.diagnostics[0].details["y_role"], "radial_outward")

    def test_non_orthogonal_axes_are_diagnostic(self) -> None:
        frame = Frame2D(
            id="bad_lcs",
            x_axis=Vector2(1.0, 0.0),
            y_axis=Vector2(1.0, 1.0),
        )

        report = verify_frame(frame)

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "non_orthogonal_axes")

    def test_zero_axis_is_diagnostic(self) -> None:
        frame = Frame2D(
            id="bad_lcs",
            x_axis=Vector2(0.0, 0.0),
            y_axis=Vector2(0.0, 1.0),
        )

        report = verify_frame(frame)

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "zero_x_axis")


if __name__ == "__main__":
    unittest.main()
