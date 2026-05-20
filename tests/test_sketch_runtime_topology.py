import unittest

from kompas_mcp.sketch_runtime import Point, Segment, SketchModel, verify_topology


class SketchRuntimeTopologyTests(unittest.TestCase):
    def test_closed_polyline_reports_ok(self) -> None:
        model = SketchModel(
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

        report = verify_topology(model, stage="after_raw_entities")

        self.assertTrue(report.ok)
        self.assertEqual(report.point_count, 4)
        self.assertEqual(report.primitive_count, 4)
        self.assertEqual(report.loops[0].loop_id, "main")
        self.assertTrue(report.loops[0].closed)
        self.assertEqual(report.loops[0].dangling_point_ids, ())
        self.assertEqual(report.to_dict()["stage"], "after_raw_entities")

    def test_open_polyline_reports_dangling_points(self) -> None:
        model = SketchModel(
            points=(
                Point("p1", 0.0, 0.0),
                Point("p2", 10.0, 0.0),
                Point("p3", 10.0, 5.0),
            ),
            primitives=(
                Segment("l1", "p1", "p2"),
                Segment("l2", "p2", "p3"),
            ),
        )

        report = verify_topology(model)

        self.assertFalse(report.ok)
        self.assertFalse(report.loops[0].closed)
        self.assertEqual(report.loops[0].dangling_point_ids, ("p1", "p3"))
        self.assertEqual(report.diagnostics[0].code, "dangling_loop_points")

    def test_missing_endpoint_is_diagnostic(self) -> None:
        model = SketchModel(
            points=(Point("p1", 0.0, 0.0),),
            primitives=(Segment("l1", "p1", "p_missing"),),
        )

        report = verify_topology(model)

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "missing_endpoint")
        self.assertEqual(report.diagnostics[0].entity_ids, ("l1",))

    def test_self_intersecting_loop_is_diagnostic(self) -> None:
        model = SketchModel(
            points=(
                Point("p1", 0.0, 0.0),
                Point("p2", 10.0, 10.0),
                Point("p3", 0.0, 10.0),
                Point("p4", 10.0, 0.0),
            ),
            primitives=(
                Segment("l1", "p1", "p2"),
                Segment("l2", "p2", "p3"),
                Segment("l3", "p3", "p4"),
                Segment("l4", "p4", "p1"),
            ),
        )

        report = verify_topology(model)

        self.assertFalse(report.ok)
        self.assertIn("unexpected_segment_intersection", [diagnostic.code for diagnostic in report.diagnostics])

    def test_construction_geometry_in_expected_loop_is_diagnostic(self) -> None:
        model = SketchModel(
            points=(
                Point("p1", 0.0, 0.0),
                Point("p2", 10.0, 0.0),
                Point("p3", 10.0, 5.0),
                Point("p4", 0.0, 5.0),
            ),
            primitives=(
                Segment("l1", "p1", "p2", construction=True),
                Segment("l2", "p2", "p3"),
                Segment("l3", "p3", "p4"),
                Segment("l4", "p4", "p1"),
            ),
        )

        report = verify_topology(model)

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "construction_in_expected_loop")


if __name__ == "__main__":
    unittest.main()
