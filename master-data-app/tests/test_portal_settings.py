import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_IMPORT = (
    "import portal.config as c; "
    "print(c.APP_ENV, c.DEMO_MODE, c.CUSTOMER_SOURCE, c.SAP_API_URL or '-', c.WORKBENCH_URL or '-', sep='|')"
)
WORKSPACES = {
    "https://adb-7181820732839861.1.azuredatabricks.net": ("test", "vhmcosd1ci"),
    "https://adb-4796304964978539.19.azuredatabricks.net": ("acc", None),
    "https://adb-4844910598668398.18.azuredatabricks.net": ("prod", None),
}


def portal_settings(host, **extra):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["DATABRICKS_HOST"] = host
    for name in (
        "MASTER_DATA_CATALOG",
        "SAP_API_URL",
        "WORKBENCH_URL",
        "CUSTOMER_SOURCE",
        "SAP_USER",
        "SAP_PASSWORD",
    ):
        env.pop(name, None)
    env.update(extra)
    result = subprocess.run(
        [sys.executable, "-c", SETTINGS_IMPORT],
        cwd=PROJECT_ROOT / "src",
        env=env,
        text=True,
        capture_output=True,
    )
    return result


class PortalSettingsTests(unittest.TestCase):
    def test_environment_follows_the_workspace(self):
        for host, (expected_env, sap_host) in WORKSPACES.items():
            with self.subTest(host=host):
                result = portal_settings(host, SAP_USER="tech-user", SAP_PASSWORD="pw")
                self.assertEqual(result.returncode, 0, result.stderr)
                app_env, demo, source, sap_url, workbench_url = result.stdout.strip().split("|")
                self.assertEqual(app_env, expected_env)
                self.assertEqual(demo, "False")
                self.assertEqual(source, "sap" if sap_host else "databricks")
                if sap_host:
                    self.assertIn(sap_host, sap_url)
                # The Workbench is the "workbench" page of this same app
                workspace = host.replace("https://adb-", "").replace(".azuredatabricks.net", "")
                self.assertEqual(workbench_url, f"https://ds-master-data-app-{workspace}.azure.databricksapps.com/workbench")

    def test_settings_can_be_overridden_by_the_environment(self):
        result = portal_settings(
            "https://adb-4796304964978539.19.azuredatabricks.net",
            SAP_API_URL="https://sap-acc.example/sap/opu/odata/sap/API_BUSINESS_PARTNER",
            WORKBENCH_URL="https://workbench.example/",
            CUSTOMER_SOURCE="databricks",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        _env, _demo, source, sap_url, workbench_url = result.stdout.strip().split("|")
        self.assertEqual(source, "databricks")
        self.assertEqual(sap_url, "https://sap-acc.example/sap/opu/odata/sap/API_BUSINESS_PARTNER")
        self.assertEqual(workbench_url, "https://workbench.example/")

    def test_sap_needs_an_endpoint_and_a_technical_user(self):
        host = "https://adb-7181820732839861.1.azuredatabricks.net"

        without_user = portal_settings(host)
        self.assertEqual(without_user.returncode, 0, without_user.stderr)
        self.assertEqual(without_user.stdout.strip().split("|")[2], "databricks")

        with_user = portal_settings(host, SAP_USER="tech-user", SAP_PASSWORD="pw")
        self.assertEqual(with_user.returncode, 0, with_user.stderr)
        self.assertEqual(with_user.stdout.strip().split("|")[2], "sap")


if __name__ == "__main__":
    unittest.main()
