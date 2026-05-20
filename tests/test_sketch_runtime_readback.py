import unittest

from kompas_mcp.sketch_runtime import (
    Arc,
    Circle,
    Point,
    Segment,
    SketchModel,
    SketchReadbackExpectation,
    verify_sketch_readback,
)


class SketchRuntimeReadbackTests(unittest.TestCase):
    def test_readback_accepts_matching_model_with_tolerance(self) -> None:
        expected = _rectangle_model()
        actual = SketchModel(
            points=(
                Point("p1", 0.0, 0.0),
                Point("p2", 10.0000001, 0.0),
                Point("p3", 10.0, 5.0),
                Point("p4", 0.0, 5.0),
            ),
            primitives=expected.primitives,
        )

        report = verify_sketch_readback(
            SketchReadbackExpectation(expected, point_tolerance=1e-5),
            actual,
            stage="after_solver",
        )

        self.assertTrue(report.ok)
        self.assertEqual(report.stage, "after_solver")
        self.assertIsNotNone(report.topology)
        self.assertEqual(report.diagnostics, ())
        self.assertEqual(report.to_dict()["actual_primitive_count"], 4)

    def test_readback_reports_missing_entities_and_coordinate_drift(self) -> None:
        expected = _rectangle_model()
        actual = SketchModel(
            points=(
                Point("p1", 0.0, 0.0),
                Point("p2", 11.0, 0.0),
                Point("p4", 0.0, 5.0),
            ),
            primitives=(Segment("l1", "p1", "p2"),),
        )

        report = verify_sketch_readback(SketchReadbackExpectation(expected), actual)
        codes = [diagnostic.code for diagnostic in report.diagnostics]

        self.assertFalse(report.ok)
        self.assertIn("readback_point_coordinate_mismatch", codes)
        self.assertIn("missing_readback_point", codes)
        self.assertIn("missing_readback_primitive", codes)
        self.assertIn("dangling_loop_points", codes)

    def test_readback_reports_primitive_mismatches(self) -> None:
        expected = SketchModel(
            points=(Point("p1", 0.0, 0.0), Point("p2", 1.0, 0.0), Point("pc", 0.5, 0.5)),
            primitives=(Arc("a1", "p1", "p2", "pc", direction="ccw", loop_id="main"),),
            expected_loops=(),
        )
        actual = SketchModel(
            points=expected.points,
            primitives=(Arc("a1", "p2", "p1", "p1", direction="cw", loop_id="helper", construction=True),),
            expected_loops=(),
        )

        report = verify_sketch_readback(SketchReadbackExpectation(expected, verify_actual_topology=False), actual)
        codes = [diagnostic.code for diagnostic in report.diagnostics]

        self.assertFalse(report.ok)
        self.assertIn("readback_primitive_endpoint_mismatch", codes)
        self.assertIn("readback_loop_mismatch", codes)
        self.assertIn("readback_construction_mismatch", codes)
        self.assertIn("readback_arc_center_mismatch", codes)
        self.assertIn("readback_arc_direction_mismatch", codes)

    def test_readback_reports_circle_mismatches(self) -> None:
        expected = SketchModel(
            points=(Point("pc", 0.0, 0.0), Point("actual_center", 1.0, 0.0)),
            primitives=(Circle("c1", "pc", 5.0),),
            expected_loops=(),
        )
        actual = SketchModel(
            points=expected.points,
            primitives=(Circle("c1", "actual_center", 6.0),),
            expected_loops=(),
        )

        report = verify_sketch_readback(SketchReadbackExpectation(expected, verify_actual_topology=False), actual)
        codes = [diagnostic.code for diagnostic in report.diagnostics]

        self.assertFalse(report.ok)
        self.assertIn("readback_circle_center_mismatch", codes)
        self.assertIn("readback_circle_radius_mismatch", codes)

    def test_readback_can_check_required_subset(self) -> None:
        expected = _rectangle_model()
        actual = SketchModel(
            points=(Point("p1", 0.0, 0.0), Point("p2", 10.0, 0.0)),
            primitives=(Segment("l1", "p1", "p2"),),
            expected_loops=(),
        )

        report = verify_sketch_readback(
            SketchReadbackExpectation(
                expected,
                required_point_ids=("p1", "p2"),
                required_primitive_ids=("l1",),
                verify_actual_topology=False,
            ),
            actual,
        )

        self.assertTrue(report.ok)


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
