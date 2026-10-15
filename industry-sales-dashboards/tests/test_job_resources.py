import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class JobRuntimeTests(unittest.TestCase):
    def test_smoke_gate_precedes_both_production_tasks_on_the_pinned_cluster(self):
        resource = yaml.safe_load((ROOT / "resources/jobs/industry_sales_refresh.job.yml").read_text())
        job = resource["resources"]["jobs"]["industry_sales_refresh"]
        self.assertEqual({task["task_key"] for task in job["tasks"]}, {"smoke_test_dashboard_sources", "refresh_cs_team_mapping", "materialize_dashboard_results"})
        self.assertEqual({task["job_cluster_key"] for task in job["tasks"]}, {"mapping_cluster"})
        self.assertEqual(len(job["job_clusters"]), 1)
        cluster = job["job_clusters"][0]["new_cluster"]
        self.assertEqual(cluster["spark_version"], "16.4.x-scala2.12")
        self.assertEqual(cluster["policy_id"], "${var.policy_id}")
        self.assertEqual(cluster["runtime_engine"], "PHOTON")
        self.assertEqual(cluster["data_security_mode"], "USER_ISOLATION")
        self.assertEqual(cluster["node_type_id"], "Standard_DS3_v2")
        self.assertEqual(cluster["autoscale"], {"min_workers": 1, "max_workers": 2})
        producer = next(task for task in job["tasks"] if task["task_key"] == "materialize_dashboard_results")
        parameters = producer["spark_python_task"]["parameters"]
        self.assertEqual(parameters[parameters.index("--warehouse-id") + 1], "${var.warehouse_id}")
        tasks = {task["task_key"]: task for task in job["tasks"]}
        self.assertEqual(tasks["refresh_cs_team_mapping"]["depends_on"], [{"task_key": "smoke_test_dashboard_sources"}])
        self.assertEqual(tasks["materialize_dashboard_results"]["depends_on"], [{"task_key": "refresh_cs_team_mapping"}])
        smoke = tasks["smoke_test_dashboard_sources"]
        self.assertEqual(smoke["timeout_seconds"], 600)
        self.assertEqual(smoke["max_retries"], 0)
        self.assertNotIn("depends_on", smoke)
        for task in job["tasks"]:
            self.assertNotIn("run_if", task)


if __name__ == "__main__":
    unittest.main()