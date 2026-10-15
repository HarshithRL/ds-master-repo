import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location("dataset_results", ROOT / "src/dataset_results.py")
results = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(results)


class DatasetResultPlanTests(unittest.TestCase):
    def test_every_dataset_has_exact_materialization_mode(self):
        plans = []
        for dashboard in ("open_orders", "quotations"):
            document = json.loads((ROOT / "source_dashboards" / f"{dashboard}.metadata.json").read_text())
            for dataset in json.loads(document["serialized_dashboard"])["datasets"]:
                plans.append(results.dataset_plan(dashboard, dataset["name"], "".join(dataset["queryLines"])))
        self.assertEqual(len(plans), 19)
        self.assertEqual(sum(plan["mode"] == "final" for plan in plans), 14)
        self.assertEqual(sum(plan["mode"] == "filtered" for plan in plans), 5)
        for plan in plans:
            if plan["mode"] == "final":
                self.assertEqual(plan["parameters"], [])
            else:
                self.assertTrue(plan["parameters"])

    def test_result_names_cannot_inject_identifiers(self):
        self.assertEqual(results.result_name("quotations", "ds_quotations"), "SC_BI_industry_sales_quotations_ds_quotations_result")
        with self.assertRaises(ValueError):
            results.result_name("quotations", "x`;drop")

    def test_all_native_compiled_consumers_keep_parameters_without_upstream_reads(self):
        schemas = json.loads((ROOT / "src/config/source_column_names.json").read_text())
        names = []
        for dashboard in ("open_orders", "quotations"):
            document = json.loads((ROOT / "source_dashboards" / f"{dashboard}.metadata.json").read_text())
            for dataset in json.loads(document["serialized_dashboard"])["datasets"]:
                with self.subTest(dashboard=dashboard, dataset=dataset["name"]):
                    plan = results.compile_dataset(dashboard, dataset["name"], "".join(dataset["queryLines"]), schemas)
                    self.assertNotIn("synapse-prd", plan["consumer_sql"])
                    self.assertNotIn("supply_chain_sandbox", plan["consumer_sql"])
                    self.assertTrue(plan["producers"])
                    for producer in plan["producers"]:
                        if producer["table"]:
                            names.append(producer["table"])
                        self.assertFalse(results.has_parameters(results.sqlglot.parse_one(producer["sql"], read="databricks")))
        from collections import Counter

        self.assertEqual({name: count for name, count in Counter(names).items() if count > 1}, {results.result_name("quotations", "shared", "converted"): 3})

    def test_missing_or_duplicate_results_cannot_publish(self):
        plans = [{"dashboard": "open_orders", "dataset": "ds_" + str(index), "producers": [{"table": "result_" + str(index), "sql": "SELECT 1"}]} for index in range(17)]
        receipts = [{"dashboard": "open_orders", "dataset": "ds_" + str(index), "table": "result_" + str(index)} for index in range(17)]
        results.validate_result_receipts(plans, receipts)
        for incomplete in (receipts[:-1], receipts + [receipts[0]], receipts[:-1] + [receipts[0]]):
            with self.subTest(receipts=incomplete), self.assertRaises(ValueError):
                results.validate_result_receipts(plans, incomplete)
        wrong_dataset = [dict(receipt) for receipt in receipts]
        wrong_dataset[0]["dashboard"] = "quotations"
        with self.assertRaises(ValueError):
            results.validate_result_receipts(plans, wrong_dataset)

    def test_shared_conversion_is_identical_independent_and_stored_once(self):
        plans = []
        schemas = json.loads((ROOT / "src/config/source_column_names.json").read_text())
        original = json.loads(json.loads((ROOT / "source_dashboards/quotations.metadata.json").read_text())["serialized_dashboard"])
        for dataset in original["datasets"]:
            plans.append(results.compile_dataset("quotations", dataset["name"], "".join(dataset["queryLines"]), schemas))
        shared = [producer for plan in plans for producer in plan["producers"] if producer.get("shared")]
        self.assertEqual(len(shared), 3)
        self.assertEqual(len({producer["table"] for producer in shared}), 1)
        self.assertEqual(len(results.unique_result_producers(plans)), 12)
        for plan in plans:
            if plan["dataset"] in results.SHARED_CONVERSION_DATASETS:
                self.assertIn(results.local_result(shared[0]["table"]), plan["consumer_sql"])
        from copy import deepcopy

        altered = deepcopy(plans)
        changed = next(producer for producer in altered[3]["producers"] if producer.get("shared"))
        changed["sql"] += " AND 1 = 0"
        with self.assertRaises(ValueError):
            results.unique_result_producers(altered)
        dependency = deepcopy(plans)
        shared_step = next(producer for producer in dependency[0]["producers"] if producer.get("shared"))
        shared_step["sql"] = "SELECT quote_number FROM converted"
        with self.assertRaises(ValueError):
            results.unique_result_producers(dependency)

    def test_date_parameter_subfields_remain_distinct(self):
        expression = results.sqlglot.parse_one("SELECT :cancel_date.min, :cancel_date.max, :segment_filter", read="databricks")
        self.assertEqual(results.parameter_contract(expression), [":cancel_date.max", ":cancel_date.min", ":segment_filter"])

    def test_final_results_preserve_user_visible_ordering(self):
        plan = results.compile_dataset("open_orders", "ds_ordered", "SELECT source.key AS order_key, SUM(source.value) AS value_eur FROM `synapse-prd`.pbi.dbx_fact_example source GROUP BY source.key ORDER BY value_eur DESC, source.key", {})
        self.assertIn("ORDER BY value_eur DESC, `order_key`", plan["consumer_sql"])


if __name__ == "__main__":
    unittest.main()