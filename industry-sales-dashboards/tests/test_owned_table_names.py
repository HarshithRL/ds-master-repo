import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dataset_results import result_name, result_storage_name, unique_result_producers
from industry_config import MAPPING_TABLE_NAME, OWNED_TABLE_PREFIX, RESULT_STATE_TABLE_NAME, validate_table_name
from sqlglot import exp, parse_one


class OwnedTableNameTests(unittest.TestCase):
    def test_complete_active_inventory_and_permission_names_match(self):
        plans = json.loads((ROOT / "src/config/dashboard_results.json").read_text())["datasets"]
        self.assertEqual(len(plans), 17)
        self.assertEqual(sum(plan["mode"] == "final" for plan in plans), 12)
        self.assertEqual(sum(plan["mode"] == "filtered" for plan in plans), 5)
        published = list(unique_result_producers(plans))
        physical = [result_storage_name(name) for name in published]
        self.assertEqual(len(set(published)), 20)
        self.assertEqual(len(set(physical)), 20)
        tables = {("silver", name) for name in physical}
        tables.add(("gold", RESULT_STATE_TABLE_NAME))
        tables.update((layer, MAPPING_TABLE_NAME) for layer in ("bronze", "silver", "gold"))
        views = {("gold", name) for name in published}
        self.assertEqual(len(tables), 24)
        self.assertEqual(len(views), 20)
        self.assertEqual(len(tables | views), 44)
        for layer, name in tables | views:
            self.assertTrue(name.startswith(OWNED_TABLE_PREFIX))
        manifest = json.loads((ROOT.parent / "permissions/access.json").read_text())
        product = next(item for item in manifest["data_products"] if item["data_product"] == "industry-sales-dashboards")
        group = next(item for item in product["consumer_groups"] if item["tier"] == "READ")
        grant_relations = {(grant["schema"], grant["table"]) for grant in group["grants"] if "table" in grant}
        self.assertEqual(grant_relations, tables | views)
        self.assertEqual(len(group["grants"]), 48)
        self.assertEqual(set(group["members"]), {"francois.leclercq@etexgroup.com", "noel.vranckx@etexgroup.com", "mustafaarda.bicakci@etexgroup.com"})

    def test_consumer_queries_use_only_prefixed_owned_tables_or_ctes(self):
        plans = json.loads((ROOT / "src/config/dashboard_results.json").read_text())["datasets"]
        for plan in plans:
            with self.subTest(dataset=plan["dataset"]):
                query = parse_one(plan["consumer_sql"], read="databricks")
                for table in query.find_all(exp.Table):
                    if table.catalog:
                        self.assertEqual(table.catalog, "${var.catalog}")
                        self.assertEqual(table.db, "gold")
                        self.assertTrue(table.name.startswith(OWNED_TABLE_PREFIX) or table.name == "${var.mapping_table_name}")
                for producer in plan["producers"]:
                    for table in parse_one(producer["sql"], read="databricks").find_all(exp.Table):
                        if table.catalog == "${var.source_catalog}":
                            self.assertTrue(table.name.startswith("dbx_"))
                            self.assertFalse(table.name.startswith(OWNED_TABLE_PREFIX))

    def test_all_active_generated_names_use_the_exact_prefix_once(self):
        published = result_name("open_orders", "ds_current_month_by_team")
        physical = result_storage_name(published)
        self.assertEqual(published, "SC_BI_industry_sales_open_orders_ds_current_month_by_team_result")
        self.assertEqual(physical, "SC_BI_industry_sales_calc_open_orders_ds_current_month_by_team_result")
        for name in (published, physical, MAPPING_TABLE_NAME, RESULT_STATE_TABLE_NAME):
            self.assertTrue(name.startswith("SC_BI_"))
            self.assertEqual(name.count(OWNED_TABLE_PREFIX), 1)

    def test_mapping_names_keep_dev_isolation_and_reject_old_names(self):
        validate_table_name(MAPPING_TABLE_NAME + "_dev", "D")
        for target in ("T", "A", "P"):
            validate_table_name(MAPPING_TABLE_NAME, target)
        for name, target in (("industry_sales_cs_team_sales_org_mapping", "A"), (MAPPING_TABLE_NAME, "D"), (MAPPING_TABLE_NAME + "_dev", "P")):
            with self.subTest(name=name, target=target), self.assertRaises(ValueError):
                validate_table_name(name, target)

    def test_physical_result_names_cannot_fall_back_to_unprefixed_outputs(self):
        for name in ("industry_sales_open_orders_ds_example_result", "SC_BI_SC_BI_industry_sales_example", "SC_BI_industry_sales_example`;DROP TABLE x"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                result_storage_name(name)


if __name__ == "__main__":
    unittest.main()