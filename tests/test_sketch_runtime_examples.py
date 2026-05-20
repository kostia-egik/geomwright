from __future__ import annotations

import unittest

from kompas_mcp.sketch_runtime import (
    DirectionAlias,
    FlatV60ThreadProfileSpec,
    Vector2,
    build_flat_v60_thread_profile_preflight,
    verify_sketch_preflight,
)


class SketchRuntimeExampleTests(unittest.TestCase):
    def test_flat_v60_profile_example_passes_preflight(self) -> None:
        plan = build_flat_v60_thread_profile_preflight(
            FlatV60ThreadProfileSpec(
                pitch=1.5,
                crest_y=10.0,
                root_y=8.7,
                outer_half_width=0.375,
                root_half_width=0.15,
            )
        )

        report = verify_sketch_preflight(plan)

        self.assertTrue(report.ok, report.to_dict())
        self.assertEqual(tuple(loop.loop_id for loop in report.topology.loops if loop.closed), ("profile",))
        self.assertEqual(report.measurements.results[0].actual, 0.75)

    def test_flat_v60_profile_example_catches_inverted_radial_alias(self) -> None:
        plan = build_flat_v60_thread_profile_preflight(
            FlatV60ThreadProfileSpec(
                pitch=1.5,
                crest_y=10.0,
                root_y=8.7,
                outer_half_width=0.375,
                root_half_width=0.15,
            )
        )
        bad_plan = type(plan)(
            **{
                **plan.__dict__,
                "direction_aliases": (
                    DirectionAlias("radial_outward", Vector2(0.0, -1.0), "+y", role="profile radial direction"),
                ),
            }
        )

        report = verify_sketch_preflight(bad_plan)

        self.assertFalse(report.ok)
        self.assertIn("direction_alias_mismatch", {diagnostic.code for diagnostic in report.diagnostics})


if __name__ == "__main__":
    unittest.main()
