import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sql_preflight", ROOT / "scripts/preflight_sql.py")
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


class SqlPreflightTests(unittest.TestCase):
    def test_every_query_can_be_analyzed_without_a_sandbox_or_target_mapping_table(self):
        mapping = [{"sales_org_code": "0012", "sales_organization": "O'Brien", "cs_team": "Europe"}]
        count = 0
        for key in ("open_orders", "quotations"):
            metadata = json.loads((ROOT / "source_dashboards" / f"{key}.metadata.json").read_text())
            for dataset in json.loads(metadata["serialized_dashboard"])["datasets"]:
                query = preflight.prepare_query("".join(dataset["queryLines"]), "synapse-prd", mapping)
                self.assertNotIn("supply_chain_sandbox_d", query)
                self.assertNotIn(":segment_filter", query)
                self.assertNotIn(":cancel_date", query)
                if "AS mapping" in query:
                    self.assertIn("O''Brien", query)
                count += 1
        self.assertEqual(count, 19)

    def test_unknown_filter_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            preflight.prepare_query("SELECT :unknown_filter", "synapse-prd", [])


if __name__ == "__main__":
    unittest.main()