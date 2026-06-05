import unittest

from kompas_mcp.section_tools import register_section_tools


class _ToolRegistry:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class SectionToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = _ToolRegistry()
        register_section_tools(self.registry)

    def test_preview_section_by_surface_operation_returns_bridge_contract(self) -> None:
        result = self.registry.tools["preview_section_by_surface_operation"](
            target_ref="spring_body",
            surface_reference="start_centerline_end_plane",
            offset_expression="(N31) * WD1",
            normal_direction="axis_positive",
            keep_side="positive",
            role="start_ground_trim",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["execution_status"], "planning_only")
        self.assertEqual(result["bridge_action_required"], "section_by_surface")
        self.assertEqual(
            result["operation"],
            {
                "operation": "section_by_surface",
                "target_ref": "spring_body",
                "surface_reference": "start_centerline_end_plane",
                "offset_expression": "(N31) * WD1",
                "normal_direction": "axis_positive",
                "keep_side": "positive",
                "role": "start_ground_trim",
            },
        )

    def test_preview_section_by_surface_requires_target_and_surface(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.tools["preview_section_by_surface_operation"]("", "surface")
        with self.assertRaises(ValueError):
            self.registry.tools["preview_section_by_surface_operation"]("target", "")


if __name__ == "__main__":
    unittest.main()
