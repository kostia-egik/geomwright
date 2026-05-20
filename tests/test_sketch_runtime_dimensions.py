import unittest

from kompas_mcp.sketch_runtime import (
    DimensionBinding,
    DimensionReadback,
    VariableSpec,
    verify_dimension_bindings,
    verify_dimension_readback,
)


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

    def test_dimension_readback_report_ok(self) -> None:
        report = verify_dimension_readback(
            variables=(VariableSpec("Pitch", 1.5),),
            dimensions=(DimensionBinding("pitch_dim", "linear", ("p1", "p2"), "Pitch"),),
            readbacks=(DimensionReadback("pitch_dim", expression="Pitch", value=1.5),),
        )

        self.assertTrue(report.ok)
        self.assertEqual(report.readback_count, 1)
        self.assertEqual(report.diagnostics, ())
        self.assertEqual(report.to_dict()["stage"], "dimension_readback")

    def test_formula_numeric_fallback_is_diagnostic(self) -> None:
        report = verify_dimension_readback(
            variables=(VariableSpec("Pitch", 1.5),),
            dimensions=(DimensionBinding("pitch_dim", "linear", ("p1", "p2"), "Pitch"),),
            readbacks=(DimensionReadback("pitch_dim", expression="1.5", value=1.5),),
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "formula_numeric_fallback")

    def test_formula_not_bound_is_diagnostic(self) -> None:
        report = verify_dimension_readback(
            variables=(VariableSpec("Pitch", 1.5), VariableSpec("Offset", 0.5)),
            dimensions=(DimensionBinding("pitch_dim", "linear", ("p1", "p2"), "Pitch", expression="Pitch + Offset"),),
            readbacks=(DimensionReadback("pitch_dim", expression="Pitch"),),
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "formula_not_bound")

    def test_dimension_value_mismatch_is_diagnostic(self) -> None:
        report = verify_dimension_readback(
            variables=(VariableSpec("Pitch", 1.5), VariableSpec("Offset", 0.5)),
            dimensions=(DimensionBinding("pitch_dim", "linear", ("p1", "p2"), "Pitch", expression="Pitch + Offset"),),
            readbacks=(DimensionReadback("pitch_dim", expression="Pitch + Offset", value=1.5),),
        )

        self.assertFalse(report.ok)
        codes = [diagnostic.code for diagnostic in report.diagnostics]
        self.assertIn("dimension_value_mismatch", codes)

    def test_missing_dimension_readback_is_diagnostic(self) -> None:
        report = verify_dimension_readback(
            variables=(VariableSpec("Pitch", 1.5),),
            dimensions=(DimensionBinding("pitch_dim", "linear", ("p1", "p2"), "Pitch"),),
            readbacks=(),
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.diagnostics[0].code, "missing_dimension_readback")


if __name__ == "__main__":
    unittest.main()
