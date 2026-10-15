import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class JobRuntimeTests(unittest.TestCase):
    def test_both_tasks_share_the_pinned_16_4_lts_cluster(self):
        resource = yaml.safe_load((ROOT / "resources/jobs/industry_sales_refresh.job.yml").read_text())
        job = resource["resources"]["jobs"]["industry_sales_refresh"]
        self.assertEqual({task["task_key"] for task in job["tasks"]}, {"refresh_cs_team_mapping", "materialize_dashboard_results"})
        self.assertEqual({task["job_cluster_key"] for task in job["tasks"]}, {"mapping_cluster"})
        self.assertEqual(len(job["job_clusters"]), 1)
        cluster = job["job_clusters"][0]["new_cluster"]
        self.assertEqual(cluster["spark_version"], "16.4.x-scala2.12")
        self.assertEqual(cluster["policy_id"], "${var.policy_id}")
        self.assertEqual(cluster["runtime_engine"], "PHOTON")
        self.assertEqual(cluster["data_security_mode"], "USER_ISOLATION")
        self.assertEqual(cluster["node_type_id"], "Standard_DS3_v2")
        self.assertEqual(cluster["autoscale"], {"min_workers": 1, "max_workers": 2})


if __name__ == "__main__":
    unittest.main()