import unittest

from kompas_mcp.sketch_runtime import (
    Arc,
    Circle,
    Point,
    Segment,
    SketchModel,
    TangencyExpectation,
    verify_tangencies,
)


class SketchRuntimeTangencyTests(unittest.TestCase):
    def test_segment_arc_tangency_report_ok(self) -> None:
        model = SketchModel(
            points=(
                Point("p0", 0.0, -1.0),
                Point("p1", 0.0, 0.0),
                Point("p2", 1.0, 1.0),
                Point("c1", 1.0, 0.0),
            ),
            primitives=(
                Segment("l1", "p0", "p1"),
                Arc("a1", "p1", "p2", "c1", direction="ccw"),
            ),
            expected_loops=(),
        )

        report = verify_tangencies(model, (TangencyExpectation("tangent_start", "l1", "a1"),))

        self.assertTrue(report.ok)
        self.assertEqual(report.tangency_count, 1)
        self.assertEqual(report.diagnostics, ())
        self.assertEqual(report.to_dict()["stage"], "tangencies")

    def test_tangency_mismatch_is_diagnostic(self) -> None:
        model = SketchModel(
            points=(
                Point("p0", -1.0, 0.0),
                Point("p1", 0.0, 0.0),
                Point("p2", 1.0, 1.0),
                Point("c1", 1.0, 0.0),
            ),
            primitives=(
                Segment("l1", "p0", "p1"),
                Arc("a1", "p1", "p2", "c1", direction="ccw"),
            ),
            expected_loops=(),
        )

        report = verify_tangencies(model, (TangencyExpectation("bad", "l1", "a1"),))

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "tangency_mismatch")

    def test_missing_tangency_primitive_is_diagnostic(self) -> None:
        model = SketchModel(
            points=(Point("p1", 0.0, 0.0),),
            primitives=(Segment("l1", "p1", "p1"),),
            expected_loops=(),
        )

        report = verify_tangencies(model, (TangencyExpectation("bad", "l1", "missing"),))

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "missing_tangency_primitive")

    def test_ambiguous_contact_point_is_diagnostic(self) -> None:
        model = SketchModel(
            points=(
                Point("p1", 0.0, 0.0),
                Point("p2", 1.0, 0.0),
                Point("p3", 2.0, 0.0),
                Point("p4", 3.0, 0.0),
            ),
            primitives=(Segment("l1", "p1", "p2"), Segment("l2", "p3", "p4")),
            expected_loops=(),
        )

        report = verify_tangencies(model, (TangencyExpectation("bad", "l1", "l2"),))

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "ambiguous_tangency_point")

    def test_circle_tangency_uses_explicit_contact_point(self) -> None:
        model = SketchModel(
            points=(
                Point("c1", 0.0, 0.0),
                Point("p1", 1.0, 0.0),
                Point("p2", 1.0, 1.0),
            ),
            primitives=(Circle("circle", "c1", 1.0), Segment("line", "p1", "p2")),
            expected_loops=(),
        )

        report = verify_tangencies(
            model,
            (TangencyExpectation("circle_line", "circle", "line", at_point_id="p1"),),
        )

        self.assertTrue(report.ok)

    def test_circle_contact_point_off_curve_is_diagnostic(self) -> None:
        model = SketchModel(
            points=(
                Point("c1", 0.0, 0.0),
                Point("p1", 2.0, 0.0),
                Point("p2", 2.0, 1.0),
            ),
            primitives=(Circle("circle", "c1", 1.0), Segment("line", "p1", "p2")),
            expected_loops=(),
        )

        report = verify_tangencies(
            model,
            (TangencyExpectation("bad", "circle", "line", at_point_id="p1"),),
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "tangency_point_off_circle")


if __name__ == "__main__":
    unittest.main()
