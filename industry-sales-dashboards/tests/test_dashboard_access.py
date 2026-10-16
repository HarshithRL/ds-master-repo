import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dashboard_access import consumer_reader_groups, dashboard_members, dashboard_relations, reader_config


class DashboardAccessTests(unittest.TestCase):
    def test_exact_unique_lists_and_common_members(self):
        config = reader_config()
        self.assertEqual(len(config["dashboards"]["open_orders"]["members"]), 118)
        self.assertEqual(len(config["dashboards"]["quotations"]["members"]), 75)
        self.assertEqual(len(dashboard_members("open_orders")), 121)
        self.assertEqual(len(dashboard_members("quotations")), 78)
        for key in config["dashboards"]:
            self.assertTrue(set(config["common_members"]).issubset(dashboard_members(key)))
            self.assertEqual(dashboard_members(key).count("ann.selderslaghs@etexgroup.com"), 1)
        self.assertNotIn("roberta.villa@etexgroup.com", dashboard_members("open_orders"))
        self.assertIn("roberta.villa@etexgroup.com", dashboard_members("quotations"))
        self.assertIn("blossom.alva@etexgroup.com", dashboard_members("open_orders"))
        self.assertNotIn("blossom.alva@etexgroup.com", dashboard_members("quotations"))

    def test_groups_only_read_their_dashboard_relations(self):
        plans = json.loads((ROOT / "src/config/dashboard_results.json").read_text())["datasets"]
        groups = consumer_reader_groups(plans)
        self.assertEqual([group["tier"] for group in groups], ["READ", "WRITE"])
        self.assertEqual([len(group["grants"]) for group in groups], [26, 32])
        for key, group in zip(("open_orders", "quotations"), groups, strict=True):
            tables = {(grant["schema"], grant["table"]) for grant in group["grants"] if "table" in grant}
            self.assertEqual(tables, dashboard_relations(plans, key))
            other = "quotations" if key == "open_orders" else "open_orders"
            self.assertFalse(any(other in table for layer, table in tables))
            for grant in group["grants"]:
                self.assertTrue(set(grant["privileges"]).issubset({"SELECT", "USE_CATALOG", "USE_SCHEMA"}))
        self.assertEqual(len(dashboard_relations(plans, "open_orders") | dashboard_relations(plans, "quotations")), 46)


if __name__ == "__main__":
    unittest.main()