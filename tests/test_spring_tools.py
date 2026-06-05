import unittest

from kompas_mcp.spring_tools import register_spring_tools


class _ToolRegistry:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class _Adapter:
    def __init__(self) -> None:
        self.calls = []

    def preview_part_scenario(self, *, scenario, params):
        self.calls.append(("preview", scenario, params))
        return {"scenario": scenario, "params": params}

    def create_part_from_scenario(self, **kwargs):
        self.calls.append(("create", kwargs))
        return kwargs


class SpringToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = _ToolRegistry()
        self.adapter = _Adapter()
        register_spring_tools(self.registry, self.adapter)

    def test_preview_compression_spring_delegates_to_fixed_scenario(self) -> None:
        result = self.registry.tools["preview_compression_spring"]({"wire_diameter": 1.2})

        self.assertEqual(result["scenario"], "compression_spring")
        self.assertEqual(self.adapter.calls, [("preview", "compression_spring", {"wire_diameter": 1.2})])

    def test_create_compression_spring_delegates_to_fixed_scenario(self) -> None:
        result = self.registry.tools["create_compression_spring"](
            {"wire_diameter": 1.2},
            output_path="out.m3d",
            visible=True,
            close_after_save=False,
            save_partial_on_error=True,
            return_partial_result_on_error=True,
        )

        self.assertEqual(result["scenario"], "compression_spring")
        self.assertEqual(result["params"], {"wire_diameter": 1.2})
        self.assertEqual(result["output_path"], "out.m3d")
        self.assertTrue(result["visible"])
        self.assertFalse(result["close_after_save"])
        self.assertTrue(result["save_partial_on_error"])
        self.assertTrue(result["return_partial_result_on_error"])


if __name__ == "__main__":
    unittest.main()
