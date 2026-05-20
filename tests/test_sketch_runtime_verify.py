import unittest

from kompas_mcp.sketch_runtime import (
    ConstraintPlan,
    ConstraintSpec,
    DimensionBinding,
    Frame2D,
    LoopOrientationExpectation,
    Point,
    PointRelationExpectation,
    Segment,
    SketchModel,
    SketchPreflightPlan,
    TangencyExpectation,
    VariableSpec,
    Vector2,
    verify_sketch_preflight,
)


class SketchRuntimePreflightTests(unittest.TestCase):
    def test_preflight_aggregates_all_reports(self) -> None:
        model = _rectangle_model()
        plan = SketchPreflightPlan(
            model=model,
            frame=Frame2D("profile_lcs", x_axis=Vector2(1.0, 0.0), y_axis=Vector2(0.0, 1.0)),
            constraints=ConstraintPlan(
                constraints=(
                    ConstraintSpec("fix_origin", "fixed", ("p1",), stage="anchor"),
                    ConstraintSpec("base_horizontal", "horizontal", ("l1",), stage="orientation"),
                )
            ),
            relations=(PointRelationExpectation("p1_left_p2", "left_of", "p1", "p2"),),
            tangencies=(TangencyExpectation("line_self_tangent", "l1", "l1", at_point_id="p2"),),
            orientations=(LoopOrientationExpectation("main", "ccw"),),
            variables=(VariableSpec("Pitch", 2.0),),
            dimensions=(DimensionBinding("pitch_dim", "linear", ("p1", "p2"), "Pitch"),),
        )

        report = verify_sketch_preflight(plan, stage="profile_preflight")

        self.assertTrue(report.ok)
        self.assertEqual(report.stage, "profile_preflight")
        self.assertIsNotNone(report.frame)
        self.assertIsNotNone(report.constraints)
        self.assertIsNotNone(report.relations)
        self.assertIsNotNone(report.tangencies)
        self.assertIsNotNone(report.orientations)
        self.assertIsNotNone(report.dimensions)
        self.assertEqual(report.diagnostics, ())
        payload = report.to_dict()
        self.assertEqual(payload["topology"]["stage"], "preflight_topology")
        self.assertIn("constraints", payload)
        self.assertIn("relations", payload)
        self.assertIn("tangencies", payload)
        self.assertIn("orientations", payload)

    def test_preflight_flattens_diagnostics(self) -> None:
        model = SketchModel(
            points=(Point("p1", 0.0, 0.0), Point("p2", 1.0, 0.0), Point("p3", 2.0, 0.0)),
            primitives=(Segment("l1", "p1", "p2"), Segment("l2", "p2", "p3")),
        )
        plan = SketchPreflightPlan(
            model=model,
            frame=Frame2D("bad_lcs", x_axis=Vector2(1.0, 0.0), y_axis=Vector2(1.0, 0.0)),
            constraints=ConstraintPlan(constraints=(ConstraintSpec("bad_parallel", "parallel", ("l1", "missing"), stage="orientation"),)),
            relations=(PointRelationExpectation("bad_relation", "right_of", "p1", "p3"),),
            tangencies=(TangencyExpectation("bad_tangent", "l1", "missing"),),
            orientations=(LoopOrientationExpectation("main", "ccw"),),
            variables=(VariableSpec("Pitch", 2.0),),
            dimensions=(DimensionBinding("bad_dim", "linear", ("missing",), "MissingVar"),),
        )

        report = verify_sketch_preflight(plan)
        codes = [diagnostic.code for diagnostic in report.diagnostics]

        self.assertFalse(report.ok)
        self.assertIn("dangling_loop_points", codes)
        self.assertIn("collinear_axes", codes)
        self.assertIn("missing_constraint_target", codes)
        self.assertIn("point_relation_mismatch", codes)
        self.assertIn("missing_tangency_primitive", codes)
        self.assertIn("orientation_open_loop", codes)
        self.assertIn("missing_dimension_variable", codes)
        self.assertIn("missing_dimension_target", codes)


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
