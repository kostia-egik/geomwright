from __future__ import annotations

import unittest

from kompas_mcp.sketch_runtime import (
    Diagnostic,
    DirectionAlias,
    FlatV60ThreadProfileSpec,
    Vector2,
    build_flat_v60_thread_profile_preflight,
    build_repair_hints,
    verify_sketch_preflight,
)


class SketchRuntimeHintTests(unittest.TestCase):
    def test_build_repair_hints_maps_known_diagnostic_codes(self) -> None:
        hints = build_repair_hints(
            (
                Diagnostic("direction_alias_mismatch", "bad direction", entity_ids=("radial_outward",)),
                Diagnostic("unknown_code", "not mapped"),
            )
        )

        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0].code, "direction_alias_mismatch")
        self.assertEqual(hints[0].entity_ids, ("radial_outward",))
        self.assertIn("local frame", hints[0].likely_cause)

    def test_build_repair_hints_deduplicates_codes(self) -> None:
        hints = build_repair_hints(
            (
                Diagnostic("missing_dimension_variable", "first", entity_ids=("dim_a",)),
                Diagnostic("missing_dimension_variable", "second", entity_ids=("dim_b",)),
            )
        )

        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0].entity_ids, ("dim_a",))

    def test_repair_hints_work_with_preflight_report(self) -> None:
        plan = build_flat_v60_thread_profile_preflight(
            FlatV60ThreadProfileSpec(pitch=1.5, crest_y=10.0, root_y=8.7, outer_half_width=0.375, root_half_width=0.15)
        )
        bad_plan = type(plan)(
            **{
                **plan.__dict__,
                "direction_aliases": (
                    DirectionAlias("radial_outward", Vector2(0.0, -1.0), "+y", role="profile radial direction"),
                ),
            }
        )

        hints = build_repair_hints(verify_sketch_preflight(bad_plan).diagnostics)

        self.assertEqual(tuple(hint.code for hint in hints), ("direction_alias_mismatch",))


if __name__ == "__main__":
    unittest.main()
