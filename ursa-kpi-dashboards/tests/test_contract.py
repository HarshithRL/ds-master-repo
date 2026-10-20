import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ursa_config import ENVIRONMENTS, quote_column, relation, table_name, validate_environment


class SourceContractTests(unittest.TestCase):
    def test_original_dashboard_inventory(self):
        source = json.loads((ROOT / "source_dashboards" / "ursa_ps4_daily_kpi_tracker.lvdash.json").read_text())
        self.assertEqual(
            {dataset["name"] for dataset in source["datasets"]},
            {
                "ursa_kpi_data", "test_invoiced_value", "hypercare_mock", "hc_baseline",
                "hc_actuals_vs_baseline", "hc_matrix_formatted", "o2c_live_matrix",
            },
        )
        self.assertEqual(len(source["datasets"]), 7)
        self.assertEqual(len(source["pages"]), 14)
        self.assertEqual(sum(len(page["layout"]) for page in source["pages"]), 50)
        self.assertTrue(all(dataset.get("queryLines") for dataset in source["datasets"]))
        self.assertTrue(all(not dataset.get("parameters") for dataset in source["datasets"]))


class EnvironmentContractTests(unittest.TestCase):
    def test_all_targets_accept_only_their_actual_workspace_and_catalog(self):
        for target, (catalog, workspace_id) in ENVIRONMENTS.items():
            with self.subTest(target=target):
                validate_environment(target, catalog, "synapse-prd", workspace_id)
                with self.assertRaises(ValueError):
                    validate_environment(target, catalog, "synapse-prd", "0")
                with self.assertRaises(ValueError):
                    validate_environment(target, "synapse-prd", "synapse-prd", workspace_id)
                with self.assertRaises(ValueError):
                    validate_environment(target, catalog, "other", workspace_id)

    def test_fixed_schemas_owned_prefix_and_dev_isolation(self):
        self.assertEqual(table_name("source_test", "D"), "URSA_KPI_source_test_dev")
        self.assertEqual(table_name("source_test", "A"), "URSA_KPI_source_test")
        self.assertEqual(relation("automation_p", "gold", "daily", "P"), "`automation_p`.`gold`.`URSA_KPI_daily`")
        for catalog, layer, component, target in (
            ("automation_a", "custom", "daily", "A"),
            ("automation_p", "gold", "daily", "A"),
            ("automation_a", "gold", "../daily", "A"),
            ("automation_a", "gold", "daily", "unknown"),
        ):
            with self.subTest(catalog=catalog, layer=layer, component=component, target=target):
                with self.assertRaises(ValueError):
                    relation(catalog, layer, component, target)

    def test_native_column_names_are_quoted_without_silent_changes(self):
        self.assertEqual(quote_column("Plant Key"), "`Plant Key`")
        for name in ("", "bad`name", "bad\x00name", None):
            with self.assertRaises(ValueError):
                quote_column(name)


if __name__ == "__main__":
    unittest.main()