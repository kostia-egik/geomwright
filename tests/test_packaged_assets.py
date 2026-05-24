from __future__ import annotations

import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from kompas_mcp import bridge_runner
from kompas_mcp import rules


class PackagedAssetsTest(unittest.TestCase):
    def test_checkout_and_packaged_assets_are_in_sync(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        pairs = [
            (
                repo_root / "rules" / "default.json",
                repo_root / "src" / "kompas_mcp" / "assets" / "rules" / "default.json",
            ),
            (
                repo_root / "bridge" / "kompas_bridge.py",
                repo_root / "src" / "kompas_mcp" / "assets" / "bridge" / "kompas_bridge.py",
            ),
        ]

        for checkout_path, packaged_path in pairs:
            with self.subTest(checkout_path=checkout_path):
                self.assertEqual(checkout_path.read_bytes(), packaged_path.read_bytes())

    def test_packaged_rules_fallback_exists(self) -> None:
        missing_checkout = Path("Z:/missing/kompas-mcp/rules/default.json")

        with patch.object(rules, "CHECKOUT_RULES_PATH", missing_checkout):
            path = rules.default_rules_path()

        self.assertEqual(path, rules.PACKAGED_RULES_PATH)
        self.assertTrue(path.exists())
        self.assertIn("naming", rules.load_rules(str(path)))

    def test_packaged_bridge_fallback_exists(self) -> None:
        missing_checkout = Path("Z:/missing/kompas-mcp/bridge/kompas_bridge.py")

        with patch.object(bridge_runner, "CHECKOUT_BRIDGE_SCRIPT", missing_checkout):
            path = bridge_runner.default_bridge_script_path()

        self.assertEqual(path, bridge_runner.PACKAGED_BRIDGE_SCRIPT)
        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size, 1000)

    def test_package_data_includes_runtime_assets(self) -> None:
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

        package_data = payload["tool"]["setuptools"]["package-data"]["kompas_mcp"]

        self.assertIn("assets/rules/*.json", package_data)
        self.assertIn("assets/bridge/*.py", package_data)


if __name__ == "__main__":
    unittest.main()
