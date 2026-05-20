import unittest

from kompas_mcp.sketch_runtime import DimensionBinding, VariableSpec, verify_dimension_bindings


class SketchRuntimeDimensionTests(unittest.TestCase):
    def test_dimension_bindings_report_ok(self) -> None:
        report = verify_dimension_bindings(
            variables=(
                VariableSpec("D1", 20.0, role="diameter"),
                VariableSpec("R1", 10.0, role="radius"),
            ),
            dimensions=(
                DimensionBinding(
                    id="dim_radius",
                    kind="axis_distance",
                    target_ids=("profile_line_1",),
                    variable="R1",
                    expression="D1 / 2",
                    role="outer_radius",
                ),
            ),
            entity_ids={"profile_line_1"},
            stage="before_apply_dimensions",
        )

        self.assertTrue(report.ok)
        self.assertEqual(report.variable_count, 2)
        self.assertEqual(report.dimension_count, 1)
        self.assertEqual(report.to_dict()["stage"], "before_apply_dimensions")

    def test_missing_dimension_variable_is_diagnostic(self) -> None:
        report = verify_dimension_bindings(
            variables=(VariableSpec("D1", 20.0),),
            dimensions=(
                DimensionBinding(
                    id="dim_radius",
                    kind="axis_distance",
                    target_ids=("profile_line_1",),
                    variable="R1",
                    expression="D1 / 2",
                ),
            ),
            entity_ids={"profile_line_1"},
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "missing_dimension_variable")

    def test_missing_target_is_diagnostic(self) -> None:
        report = verify_dimension_bindings(
            variables=(VariableSpec("L1", 30.0),),
            dimensions=(
                DimensionBinding(
                    id="dim_length",
                    kind="line_length",
                    target_ids=("profile_line_missing",),
                    variable="L1",
                ),
            ),
            entity_ids={"profile_line_1"},
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "missing_dimension_target")

    def test_unknown_expression_reference_is_diagnostic(self) -> None:
        report = verify_dimension_bindings(
            variables=(VariableSpec("R1", 10.0),),
            dimensions=(
                DimensionBinding(
                    id="dim_radius",
                    kind="axis_distance",
                    target_ids=("profile_line_1",),
                    variable="R1",
                    expression="D1 / 2",
                ),
            ),
            entity_ids={"profile_line_1"},
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "unknown_expression_reference")


if __name__ == "__main__":
    unittest.main()
