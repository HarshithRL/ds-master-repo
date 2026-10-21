import ast
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml


ROOT = Path(__file__).resolve().parents[1]


class BundleContractTests(unittest.TestCase):
    def test_existing_environment_and_warehouse_bindings_are_explicit(self):
        bundle = yaml.safe_load((ROOT / "databricks.yml").read_text())
        self.assertEqual(bundle["bundle"]["name"], "ursa-kpi-dashboards")
        self.assertEqual(set(bundle["targets"]), {"D", "T", "A", "P"})
        for target, catalog in (("D", "automation_d"), ("T", "automation_d"), ("A", "automation_a"), ("P", "automation_p")):
            variables = bundle["targets"][target]["variables"]
            self.assertEqual(variables["catalog"], catalog)
            self.assertEqual(variables["refresh_pause_status"], "PAUSED" if target in ("D", "T") else "UNPAUSED")
        self.assertEqual(bundle["targets"]["D"]["variables"]["result_suffix"], "_dev")
        self.assertEqual(bundle["targets"]["A"]["variables"]["warehouse_id"], "0ef3e37fbbd5b772")
        self.assertEqual(bundle["targets"]["P"]["variables"]["warehouse_id"], "f500d0d670ae024b")
        for include in bundle["include"]:
            self.assertNotIn("*", include)
            self.assertTrue((ROOT / include).is_file())
            self.assertNotIn("permissions", include)

    def test_consumer_dashboard_access_is_limited_to_acc_and_prd(self):
        bundle = yaml.safe_load((ROOT / "databricks.yml").read_text())
        expected = [
            {"group_name": "AUTOMATION.URSAKPIDASHBOARDS.CONSUMER.READ", "level": "CAN_READ"},
            {"group_name": "AUTOMATION.URSAKPIDASHBOARDS.CONSUMER.WRITE", "level": "CAN_READ"},
        ]
        for target in ("A", "P"):
            with self.subTest(target=target):
                self.assertEqual(bundle["targets"][target]["resources"], {
                    "dashboards": {"ursa_ps4_daily_kpi_tracker": {"permissions": expected}},
                })
        for target in ("D", "T"):
            self.assertNotIn("resources", bundle["targets"][target])
        self.assertEqual(bundle["permissions"], [
            {"user_name": "mustafaarda.bicakci@etexgroup.com", "level": "CAN_MANAGE"},
            {"user_name": "pierre.delaguiche@etexgroup.com", "level": "CAN_MANAGE"},
        ])
        job = yaml.safe_load((ROOT / "resources" / "jobs" / "ursa_kpi_refresh.job.yml").read_text())
        self.assertNotIn("AUTOMATION.URSAKPIDASHBOARDS", json.dumps(job))

    def test_refresh_graph_has_preflight_materialization_and_native_readback(self):
        definition = yaml.safe_load((ROOT / "resources" / "jobs" / "ursa_kpi_refresh.job.yml").read_text())
        job = definition["resources"]["jobs"]["ursa_kpi_refresh"]
        self.assertEqual(job["max_concurrent_runs"], 1)
        self.assertEqual(job["schedule"], {
            "quartz_cron_expression": "0 30 6 * * ?",
            "timezone_id": "Europe/Brussels",
            "pause_status": "${var.refresh_pause_status}",
        })
        tasks = job["tasks"]
        self.assertEqual([task["task_key"] for task in tasks], ["preflight_sources", "materialize_results", "verify_dashboard_results"])
        self.assertEqual(tasks[1]["depends_on"], [{"task_key": "preflight_sources"}])
        self.assertEqual(tasks[2]["depends_on"], [{"task_key": "materialize_results"}])
        for task in tasks:
            self.assertIn("--config-path", task["spark_python_task"]["parameters"])
            self.assertTrue((ROOT / "resources" / "jobs" / task["spark_python_task"]["python_file"]).is_file())
            self.assertEqual(task["libraries"], [{"pypi": {"package": "sqlglot==27.20.0"}}])

    def test_runtime_contains_no_schema_creation_or_drop_commands(self):
        for path in (ROOT / "src").rglob("*.py"):
            tree = ast.parse(path.read_text())
            strings = [node.value.upper() for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
            self.assertFalse(any("CREATE SCHEMA" in text or "CREATE DATABASE" in text or "DROP TABLE" in text or "DROP VIEW" in text for text in strings), str(path))

    def test_databricks_exec_wrapper_does_not_need_file_global(self):
        path = ROOT / "src" / "notebooks" / "refresh_ursa_kpi.py"
        runtime = Mock()
        spark = Mock()
        session = Mock()
        session.builder.getOrCreate.return_value = spark
        pyspark = types.ModuleType("pyspark")
        sql = types.ModuleType("pyspark.sql")
        sql.SparkSession = session
        args = [str(path), "--catalog", "automation_d", "--source-catalog", "synapse-prd", "--target", "D", "--config-path", str(ROOT / "src" / "config"), "--mode", "preflight"]
        with patch.dict(sys.modules, {"pyspark": pyspark, "pyspark.sql": sql}), patch.object(sys, "argv", args), patch("ursa_runtime.execute", runtime):
            exec(compile(path.read_text(), str(path), "exec"), {"__name__": "__main__"})
        runtime.assert_called_once_with(spark, str(ROOT / "src" / "config"), "automation_d", "synapse-prd", "D", "preflight")


if __name__ == "__main__":
    unittest.main()