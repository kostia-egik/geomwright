from __future__ import annotations

import unittest

from kompas_mcp.materials import resolve_material_payload


class MaterialNormalizationTests(unittest.TestCase):
    def test_known_alias_is_normalized_to_catalog_name(self) -> None:
        payload = resolve_material_payload("Steel 45")

        self.assertEqual(payload["material"], "Сталь 45 ГОСТ 1050-2013")
        self.assertAlmostEqual(payload["density"], 7.85)
        self.assertTrue(payload["catalog_matched"])

    def test_explicit_density_overrides_catalog_default(self) -> None:
        payload = resolve_material_payload("Сталь 45", density=7.9)

        self.assertEqual(payload["material"], "Сталь 45 ГОСТ 1050-2013")
        self.assertAlmostEqual(payload["density"], 7.9)
        self.assertTrue(payload["catalog_matched"])


if __name__ == "__main__":
    unittest.main()
