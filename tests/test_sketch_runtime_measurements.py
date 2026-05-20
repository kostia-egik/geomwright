import unittest

from kompas_mcp.sketch_runtime import (
    Arc,
    Circle,
    MeasurementExpectation,
    Point,
    Segment,
    SketchModel,
    verify_measurements,
)


class SketchRuntimeMeasurementTests(unittest.TestCase):
    def test_measurements_report_ok(self) -> None:
        model = SketchModel(
            points=(
                Point("p1", 0.0, 0.0),
                Point("p2", 3.0, 4.0),
                Point("center", 0.0, 0.0),
                Point("arc_start", 2.0, 0.0),
                Point("arc_end", 0.0, 2.0),
            ),
            primitives=(
                Segment("line", "p1", "p2"),
                Arc("arc", "arc_start", "arc_end", "center"),
                Circle("circle", "center", 2.0),
            ),
            expected_loops=(),
        )

        report = verify_measurements(
            model,
            (
                MeasurementExpectation("distance", "point_distance", ("p1", "p2"), 5.0),
                MeasurementExpectation("dx", "horizontal_distance", ("p1", "p2"), 3.0),
                MeasurementExpectation("dy", "vertical_distance", ("p1", "p2"), 4.0),
                MeasurementExpectation("line_length", "segment_length", ("line",), 5.0),
                MeasurementExpectation("arc_radius", "arc_radius", ("arc",), 2.0),
                MeasurementExpectation("circle_radius", "circle_radius", ("circle",), 2.0),
            ),
        )

        self.assertTrue(report.ok)
        self.assertEqual(len(report.results), 6)
        self.assertEqual(report.diagnostics, ())
        self.assertEqual(report.to_dict()["stage"], "measurements")

    def test_measurement_mismatch_is_diagnostic(self) -> None:
        model = SketchModel(points=(Point("p1", 0.0, 0.0), Point("p2", 1.0, 0.0)), expected_loops=())

        report = verify_measurements(
            model,
            (MeasurementExpectation("bad", "point_distance", ("p1", "p2"), 2.0),),
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "measurement_mismatch")

    def test_missing_measurement_target_is_diagnostic(self) -> None:
        model = SketchModel(points=(Point("p1", 0.0, 0.0),), expected_loops=())

        report = verify_measurements(
            model,
            (MeasurementExpectation("bad", "point_distance", ("p1", "missing"), 1.0),),
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "missing_measurement_target")

    def test_measurement_target_count_mismatch_is_diagnostic(self) -> None:
        model = SketchModel(points=(Point("p1", 0.0, 0.0),), expected_loops=())

        report = verify_measurements(
            model,
            (MeasurementExpectation("bad", "point_distance", ("p1",), 1.0),),
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "measurement_target_count_mismatch")

    def test_measurement_target_kind_mismatch_is_diagnostic(self) -> None:
        model = SketchModel(
            points=(Point("p1", 0.0, 0.0), Point("p2", 1.0, 0.0)),
            primitives=(Segment("line", "p1", "p2"),),
            expected_loops=(),
        )

        report = verify_measurements(
            model,
            (MeasurementExpectation("bad", "circle_radius", ("line",), 1.0),),
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "measurement_target_kind_mismatch")

    def test_inconsistent_arc_radius_is_diagnostic(self) -> None:
        model = SketchModel(
            points=(Point("center", 0.0, 0.0), Point("start", 1.0, 0.0), Point("end", 0.0, 2.0)),
            primitives=(Arc("arc", "start", "end", "center"),),
            expected_loops=(),
        )

        report = verify_measurements(
            model,
            (MeasurementExpectation("bad", "arc_radius", ("arc",), 1.0),),
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "arc_radius_inconsistent")


if __name__ == "__main__":
    unittest.main()
