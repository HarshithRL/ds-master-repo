import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path

import sqlglot
from sqlglot import exp


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ursa_plan import collect_source_columns, compile_dashboard, consumer_query, freeze_business_date, input_view, localize_sources, parse_query, source_identity


class ProjectionTests(unittest.TestCase):
    def test_only_required_join_filter_and_calculated_fields_are_projected(self):
        statement = "SELECT first.`Value` * second.`Rate` AS amount FROM `synapse-prd`.pbi.fact first JOIN `synapse-prd`.pbi.rates second ON first.`Rate Key` = second.`Key` WHERE first.`Date` >= CURRENT_DATE()"
        sources = {source["identity"]: source["columns"] for source in collect_source_columns([statement])}
        self.assertEqual(sources, {"synapse-prd.pbi.fact": ["Date", "Rate Key", "Value"], "synapse-prd.pbi.rates": ["Key", "Rate"]})

    def test_inherited_ctes_are_not_mistaken_for_selected_inputs(self):
        statement = "WITH previous AS (SELECT 1 AS unrelated), result AS (SELECT `Required` FROM `synapse-prd`.pbi.fact) SELECT * FROM result"
        self.assertEqual(collect_source_columns([statement])[0]["columns"], ["Required"])

    def test_raw_wildcards_and_ambiguous_columns_fail_closed(self):
        for statement in (
            "SELECT * FROM `synapse-prd`.pbi.fact",
            "SELECT fact.* FROM `synapse-prd`.pbi.fact",
            "SELECT missing FROM `synapse-prd`.pbi.fact first JOIN `synapse-prd`.pbi.other second ON first.id = second.id",
        ):
            with self.subTest(statement=statement):
                with self.assertRaises(ValueError):
                    collect_source_columns([statement])

    def test_native_schema_resolves_unique_unqualified_owners(self):
        statement = "SELECT wanted FROM `synapse-prd`.pbi.fact first JOIN `synapse-prd`.pbi.other second ON first.id = second.id"
        sources = collect_source_columns([statement], {"synapse-prd.pbi.fact": ["id", "wanted"], "synapse-prd.pbi.other": ["id"]})
        self.assertEqual(sources[0]["columns"], ["id", "wanted"])
        with self.assertRaises(ValueError):
            collect_source_columns(["SELECT missing FROM `synapse-prd`.pbi.fact"], {"synapse-prd.pbi.fact": ["id"]})

    def test_undeclared_catalogs_and_mutating_or_parameterized_sql_are_rejected(self):
        for statement in ("SELECT value FROM `personal_catalog`.pbi.fact", "SELECT value FROM fact"):
            with self.assertRaises(ValueError):
                collect_source_columns([statement])
        for statement in ("DROP TABLE t", "SELECT 1; SELECT 2", "SELECT :region"):
            with self.assertRaises(ValueError):
                parse_query(statement)

    def test_source_rewrite_changes_relations_not_literals_or_comments(self):
        statement = "SELECT value, 'synapse-prd.pbi.fact' AS label FROM `synapse-prd`.pbi.fact -- keep formula\n"
        result = localize_sources(statement)
        self.assertIn("'synapse-prd.pbi.fact'", result)
        self.assertIn("-- keep formula", result)
        self.assertIn("FROM `URSA_KPI_input_source_pbi_fact`", result)

    def test_business_date_is_frozen_without_changing_string_literals(self):
        result = freeze_business_date("SELECT CURRENT_DATE(), current_date, 'CURRENT_DATE()' AS original", date(2026, 10, 20))
        parsed = sqlglot.parse_one(result, read="databricks")
        self.assertFalse(list(parsed.find_all(exp.CurrentDate)))
        self.assertIn("'CURRENT_DATE()'", result)
        self.assertEqual(result.count("'2026-10-20'"), 2)

    def test_result_order_uses_output_aliases(self):
        result = consumer_query("SELECT SUM(f.value) AS total FROM `synapse-prd`.pbi.fact f ORDER BY SUM(f.value) DESC", "result_summary")
        self.assertIn("ORDER BY `total` DESC", result)


class NativeDashboardPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((ROOT / "source_dashboards" / "ursa_ps4_daily_kpi_tracker.lvdash.json").read_text())
        cls.compiled, cls.plan = compile_dashboard(cls.source)

    def test_all_original_presentation_and_dataset_metadata_are_unchanged(self):
        self.assertEqual(self.compiled["pages"], self.source["pages"])
        self.assertEqual(self.compiled.get("uiSettings"), self.source.get("uiSettings"))
        original_metadata = copy.deepcopy(self.source["datasets"])
        compiled_metadata = copy.deepcopy(self.compiled["datasets"])
        for dataset in original_metadata + compiled_metadata:
            dataset.pop("query", None)
            dataset.pop("queryLines", None)
        self.assertEqual(compiled_metadata, original_metadata)
        self.assertEqual(self.plan["source_inventory"], {"datasets": 7, "pages": 14, "widgets": 50})

    def test_every_dataset_reads_only_one_local_gold_result(self):
        self.assertEqual(len(self.plan["datasets"]), 7)
        for dataset in self.compiled["datasets"]:
            query = parse_query("".join(dataset["queryLines"]))
            tables = list(query.find_all(exp.Table))
            self.assertEqual(len(tables), 1)
            self.assertEqual(tables[0].catalog, "${var.catalog}")
            self.assertEqual(tables[0].db, "gold")
            self.assertTrue(tables[0].name.startswith("URSA_KPI_result_"))

    def test_source_projections_are_nonempty_bounded_and_localized(self):
        self.assertGreater(len(self.plan["sources"]), 0)
        for source in self.plan["sources"]:
            self.assertTrue(source["columns"])
            self.assertEqual(len(source["columns"]), len(set(source["columns"])))
            self.assertNotIn("*", source["columns"])
        for dataset in self.plan["datasets"]:
            query = parse_query(dataset["local_sql"])
            self.assertFalse(any(table.catalog for table in query.find_all(exp.Table)))

    def test_all_native_formulas_joins_filters_and_ordering_are_unchanged(self):
        for dataset in self.plan["datasets"]:
            with self.subTest(dataset=dataset["dataset"]):
                expected = parse_query(dataset["source_sql"])
                for table in expected.find_all(exp.Table):
                    if table.catalog:
                        identity = source_identity(table)
                        table.set("catalog", None)
                        table.set("db", None)
                        table.set("this", exp.Identifier(this=input_view(identity), quoted=True))
                actual = parse_query(dataset["local_sql"])
                self.assertEqual(actual.sql(dialect="databricks", comments=False), expected.sql(dialect="databricks", comments=False))


if __name__ == "__main__":
    unittest.main()