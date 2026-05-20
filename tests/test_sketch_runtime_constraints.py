import unittest

from kompas_mcp.sketch_runtime import (
    ConstraintPlan,
    ConstraintSpec,
    ConstraintStageSpec,
    verify_constraint_plan,
)


class SketchRuntimeConstraintTests(unittest.TestCase):
    def test_valid_constraint_plan_reports_ok_and_order(self) -> None:
        plan = ConstraintPlan(
            constraints=(
                ConstraintSpec("dim_pitch", "distance", ("p1", "p2"), stage="driving_dimensions"),
                ConstraintSpec("coincide_start", "coincident", ("p1", "p2"), stage="anchor"),
                ConstraintSpec("horizontal_base", "horizontal", ("l1",), stage="orientation"),
            ),
            stages=(
                ConstraintStageSpec("anchor", required_ids=("coincide_start",), expected_count=1),
                ConstraintStageSpec("orientation", expected_count=1),
                ConstraintStageSpec("driving_dimensions", expected_count=1),
            ),
        )

        report = verify_constraint_plan(plan, entity_ids={"p1", "p2", "l1"})

        self.assertTrue(report.ok)
        self.assertEqual(report.constraint_count, 3)
        self.assertEqual([constraint.id for constraint in plan.ordered_constraints()], ["coincide_start", "horizontal_base", "dim_pitch"])
        self.assertEqual(report.stages[0].constraint_ids, ("coincide_start",))

    def test_missing_constraint_target_is_diagnostic(self) -> None:
        plan = ConstraintPlan(
            constraints=(ConstraintSpec("parallel_refs", "parallel", ("l1", "missing"), stage="orientation"),),
            stages=(ConstraintStageSpec("orientation"),),
        )

        report = verify_constraint_plan(plan, entity_ids={"l1"})

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "missing_constraint_target")
        self.assertEqual(report.diagnostics[0].entity_ids, ("parallel_refs",))

    def test_required_constraint_wrong_stage_is_diagnostic(self) -> None:
        plan = ConstraintPlan(
            constraints=(ConstraintSpec("fix_origin", "fixed", ("p1",), stage="shape"),),
            stages=(
                ConstraintStageSpec("anchor", required_ids=("fix_origin",)),
                ConstraintStageSpec("shape"),
            ),
        )

        report = verify_constraint_plan(plan, entity_ids={"p1"})

        self.assertFalse(report.ok)
        self.assertEqual(report.stages[0].diagnostics[0].code, "required_constraint_wrong_stage")

    def test_constraint_kind_minimum_target_count_is_checked(self) -> None:
        plan = ConstraintPlan(
            constraints=(ConstraintSpec("bad_tangent", "tangent", ("arc1",), stage="shape"),),
            stages=(ConstraintStageSpec("shape"),),
        )

        report = verify_constraint_plan(plan, entity_ids={"arc1"})

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "constraint_target_count")

    def test_unknown_stage_is_diagnostic(self) -> None:
        plan = ConstraintPlan(
            constraints=(ConstraintSpec("c1", "fixed", ("p1",), stage="unknown"),),
            stages=(ConstraintStageSpec("anchor"),),
        )

        report = verify_constraint_plan(plan, entity_ids={"p1"})

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "unknown_constraint_stage")


if __name__ == "__main__":
    unittest.main()
