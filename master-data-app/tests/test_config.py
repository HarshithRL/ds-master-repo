import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_IMPORT = "import config; print(config.UNITY_CATALOG)"
WORKSPACE_CATALOGS = {
    "https://adb-7181820732839861.1.azuredatabricks.net": "automation_d",
    "https://adb-4796304964978539.19.azuredatabricks.net": "automation_a",
    "https://adb-4844910598668398.18.azuredatabricks.net": "automation_p",
}


def import_config(host, catalog=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["DATABRICKS_HOST"] = host
    env.pop("MASTER_DATA_CATALOG", None)
    if catalog is not None:
        env["MASTER_DATA_CATALOG"] = catalog
    return subprocess.run(
        [sys.executable, "-c", CONFIG_IMPORT],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )


class ConfigEnvironmentTests(unittest.TestCase):
    def test_maps_each_workspace_to_its_automation_catalog(self):
        for host, expected_catalog in WORKSPACE_CATALOGS.items():
            with self.subTest(host=host):
                result = import_config(host)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected_catalog)

    def test_unknown_workspace_requires_an_explicit_catalog(self):
        result = import_config("https://unknown.example")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not determine the Master Data catalog", result.stderr)

    def test_catalog_override_must_match_workspace(self):
        host = "https://adb-4796304964978539.19.azuredatabricks.net"
        result = import_config(host, "automation_d")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match the Databricks workspace", result.stderr)


if __name__ == "__main__":
    unittest.main()