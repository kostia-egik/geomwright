from __future__ import annotations

import unittest

from kompas_mcp.sketch_runtime import (
    DirectionAlias,
    FlatV60ThreadProfileSpec,
    SketchReadbackExpectation,
    Vector2,
    build_flat_v60_thread_profile_preflight,
    build_preflight_state_card,
    build_readback_state_card,
    verify_sketch_preflight,
    verify_sketch_readback,
)


class SketchRuntimeStateCardTests(unittest.TestCase):
    def test_preflight_state_card_summarizes_ok_report(self) -> None:
        plan = build_flat_v60_thread_profile_preflight(
            FlatV60ThreadProfileSpec(pitch=1.5, crest_y=10.0, root_y=8.7, outer_half_width=0.375, root_half_width=0.15)
        )
        report = verify_sketch_preflight(plan, stage="example_preflight")

        card = build_preflight_state_card(report)

        self.assertTrue(card.ok)
        self.assertEqual(card.stage, "example_preflight")
        self.assertEqual(card.closed_loops, ("profile",))
        self.assertTrue(card.sections["topology"])
        self.assertTrue(card.sections["dimensions"])
        self.assertEqual(card.diagnostic_codes, ())

    def test_preflight_state_card_summarizes_failures(self) -> None:
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

        card = build_preflight_state_card(verify_sketch_preflight(bad_plan))

        self.assertFalse(card.ok)
        self.assertFalse(card.sections["direction_aliases"])
        self.assertEqual(card.diagnostic_codes, ("direction_alias_mismatch",))
        self.assertEqual(card.diagnostic_entities, ("radial_outward",))

    def test_readback_state_card_summarizes_actual_snapshot(self) -> None:
        plan = build_flat_v60_thread_profile_preflight(
            FlatV60ThreadProfileSpec(pitch=1.5, crest_y=10.0, root_y=8.7, outer_half_width=0.375, root_half_width=0.15)
        )
        report = verify_sketch_readback(SketchReadbackExpectation(plan.model), plan.model, stage="example_readback")

        card = build_readback_state_card(report)

        self.assertTrue(card.ok)
        self.assertEqual(card.stage, "example_readback")
        self.assertEqual(card.point_count, 6)
        self.assertEqual(card.primitive_count, 4)
        self.assertEqual(card.closed_loops, ("profile",))


if __name__ == "__main__":
    unittest.main()
