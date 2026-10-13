import importlib.util
import json
import unittest
from datetime import date
from pathlib import Path

import sqlglot
from sqlglot import exp


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("allocation_stages", ROOT / "src/allocation_stages.py")
staging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(staging)


class AllocationStageTests(unittest.TestCase):
    def test_every_original_cte_expression_is_preserved(self):
        metadata = json.loads((ROOT / "source_dashboards/open_orders.metadata.json").read_text())
        dataset = next(item for item in json.loads(metadata["serialized_dashboard"])["datasets"] if item["name"] == "ds_overview_allocation")
        source = "".join(dataset["queryLines"])
        original = sqlglot.parse_one(source, read="databricks")
        business_date = date(2026, 10, 13)
        stages, final = staging.build_stages(source, business_date)
        originals = original.args["with"].expressions
        self.assertEqual([cte.alias_or_name for cte in originals], [name for name, statement in stages])
        for cte, (name, statement) in zip(originals, stages, strict=True):
            expected = staging.freeze_date(cte.this.copy(), business_date)
            actual = sqlglot.parse_one(statement, read="databricks")
            self.assertEqual(expected, actual, name)
        original.set("with", None)
        self.assertEqual(staging.freeze_date(original, business_date), sqlglot.parse_one(final, read="databricks"))
        self.assertFalse(any(sqlglot.parse_one(statement, read="databricks").find(exp.CurrentDate) for name, statement in stages))

    def test_isolated_output_names(self):
        mapping = "industry_sales_cs_team_sales_org_mapping"
        self.assertEqual(staging.output_table_name(mapping), "industry_sales_open_orders_allocation")
        self.assertEqual(staging.output_table_name(mapping + "_dev"), "industry_sales_open_orders_allocation_dev")
        with self.assertRaises(ValueError):
            staging.output_table_name("unrelated_table")

    def test_missing_or_recursive_ctes_are_rejected(self):
        for query in ("SELECT 1", "WITH RECURSIVE counter AS (SELECT 1) SELECT * FROM counter"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                staging.build_stages(query, date(2026, 10, 13))


if __name__ == "__main__":
    unittest.main()