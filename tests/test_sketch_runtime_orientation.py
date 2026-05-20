import unittest

from kompas_mcp.sketch_runtime import (
    Arc,
    LoopOrientationExpectation,
    Point,
    Segment,
    SketchModel,
    verify_loop_orientations,
)


class SketchRuntimeOrientationTests(unittest.TestCase):
    def test_ccw_segment_loop_reports_ok(self) -> None:
        report = verify_loop_orientations(
            _rectangle_model(),
            (LoopOrientationExpectation("main", "ccw"),),
            stage="after_topology",
        )

        self.assertTrue(report.ok)
        self.assertEqual(report.stage, "after_topology")
        self.assertEqual(report.results[0].actual, "ccw")
        self.assertGreater(report.results[0].signed_area or 0.0, 0.0)
        self.assertIn("results", report.to_dict())

    def test_orientation_mismatch_is_diagnostic(self) -> None:
        report = verify_loop_orientations(_rectangle_model(), (LoopOrientationExpectation("main", "cw"),))

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "loop_orientation_mismatch")

    def test_orientation_rejects_open_loop(self) -> None:
        model = SketchModel(
            points=(Point("p1", 0.0, 0.0), Point("p2", 1.0, 0.0), Point("p3", 1.0, 1.0)),
            primitives=(Segment("l1", "p1", "p2"), Segment("l2", "p2", "p3")),
        )

        report = verify_loop_orientations(model, (LoopOrientationExpectation(),))

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "orientation_open_loop")

    def test_orientation_rejects_unsupported_arc_loop(self) -> None:
        model = SketchModel(
            points=(Point("p1", 0.0, 0.0), Point("p2", 1.0, 0.0), Point("pc", 0.5, 0.5)),
            primitives=(Arc("a1", "p1", "p2", "pc"),),
            expected_loops=(),
        )

        report = verify_loop_orientations(model, (LoopOrientationExpectation(),))

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "orientation_unsupported_primitive")


def _rectangle_model() -> SketchModel:
    return SketchModel(
        points=(
            Point("p1", 0.0, 0.0),
            Point("p2", 10.0, 0.0),
            Point("p3", 10.0, 5.0),
            Point("p4", 0.0, 5.0),
        ),
        primitives=(
            Segment("l1", "p1", "p2"),
            Segment("l2", "p2", "p3"),
            Segment("l3", "p3", "p4"),
            Segment("l4", "p4", "p1"),
        ),
    )


if __name__ == "__main__":
    unittest.main()
