import unittest

from kompas_mcp.sketch_runtime import (
    Point,
    PointRelationExpectation,
    SketchModel,
    verify_point_relations,
)


class SketchRuntimeRelationsTests(unittest.TestCase):
    def test_point_relations_report_ok(self) -> None:
        model = SketchModel(
            points=(Point("left", 0.0, 0.0), Point("right", 10.0, 0.0), Point("top", 10.0, 5.0)),
            expected_loops=(),
        )

        report = verify_point_relations(
            model,
            (
                PointRelationExpectation("left_before_right", "left_of", "left", "right", min_delta=10.0),
                PointRelationExpectation("top_above_right", "above", "top", "right", min_delta=5.0),
                PointRelationExpectation("left_same_y_right", "same_y", "left", "right"),
            ),
        )

        self.assertTrue(report.ok)
        self.assertEqual(report.relation_count, 3)
        self.assertEqual(report.diagnostics, ())
        self.assertEqual(report.to_dict()["stage"], "point_relations")

    def test_point_relation_mismatch_is_diagnostic(self) -> None:
        model = SketchModel(points=(Point("a", 0.0, 0.0), Point("b", 1.0, 0.0)), expected_loops=())

        report = verify_point_relations(model, (PointRelationExpectation("a_right_b", "right_of", "a", "b"),))

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "point_relation_mismatch")

    def test_missing_relation_target_is_diagnostic(self) -> None:
        model = SketchModel(points=(Point("a", 0.0, 0.0),), expected_loops=())

        report = verify_point_relations(model, (PointRelationExpectation("bad", "above", "a", "missing"),))

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "missing_point_relation_target")


if __name__ == "__main__":
    unittest.main()
