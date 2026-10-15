import importlib.util
import json
import sys
import unittest
from pathlib import Path

import sqlglot
from sqlglot import exp


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location("source_snapshots", ROOT / "src/source_snapshots.py")
snapshots = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshots)


def statements():
    queries = []
    for key in ("open_orders", "quotations"):
        metadata = json.loads((ROOT / "source_dashboards" / f"{key}.metadata.json").read_text())
        queries.extend("".join(dataset["queryLines"]) for dataset in json.loads(metadata["serialized_dashboard"])["datasets"])
    return queries


class SourceSnapshotTests(unittest.TestCase):
    def test_all_fourteen_sources_are_discovered(self):
        planned = snapshots.collect_source_columns(statements())
        expected = json.loads((ROOT / "src/config/source_dependencies.json").read_text())["pbi_tables"]
        self.assertEqual([source["source_table"] for source in planned], expected)
        self.assertEqual(len({source["snapshot_table"] for source in planned}), 14)

    def test_native_sales_fact_copies_required_fields_not_every_source_column(self):
        source_schemas = json.loads((ROOT / "src/config/source_column_names.json").read_text())
        planned = snapshots.collect_source_columns(statements(), source_schemas)
        fact = next(source for source in planned if source["source_table"] == "dbx_fact_sales_distribution_sales_document_item")
        self.assertIsNotNone(fact["columns"], "Native source aliases should not force the 297-column fallback")
        self.assertEqual(len(fact["columns"]), 31)
        for column in ("Sales Document Number", "Sales Document Item Number", "Quote Number", "Created On", "Measure Net Value in Euro"):
            self.assertIn(column, fact["columns"])

    def test_inherited_ctes_are_not_selected_input_tables(self):
        query = "WITH other AS (SELECT * FROM `synapse-prd`.pbi.dbx_fact_other) SELECT `Date Key` FROM `synapse-prd`.pbi.dbx_date_example"
        planned = {source["source_table"]: source for source in snapshots.collect_source_columns([query])}
        self.assertEqual(planned["dbx_date_example"]["columns"], ["Date Key"])

    def test_unknown_or_ambiguous_schema_keeps_all_fields(self):
        query = "SELECT `Created On` FROM `synapse-prd`.pbi.dbx_fact_example fact JOIN `synapse-prd`.pbi.dbx_dim_example dim ON fact.`Join Key`=dim.`Join Key`"
        for schemas in (None, {"dbx_fact_example": ["Created On"]}, {"dbx_fact_example": ["Created On"], "dbx_dim_example": ["Created On"]}):
            with self.subTest(schemas=schemas):
                self.assertTrue(all(source["columns"] is None for source in snapshots.collect_source_columns([query], schemas)))
        planned = {source["source_table"]: source for source in snapshots.collect_source_columns([query], {"dbx_fact_example": ["Created On"], "dbx_dim_example": []})}
        self.assertEqual(planned["dbx_fact_example"]["columns"], ["Created On", "Join Key"])
        self.assertEqual(planned["dbx_dim_example"]["columns"], ["Join Key"])

    def test_only_source_table_locations_change(self):
        for index, source in enumerate(statements()):
            with self.subTest(query=index):
                original = sqlglot.parse_one(source, read="databricks")
                expected = original.copy()
                for table in expected.find_all(exp.Table):
                    if snapshots.is_source(table):
                        table.set("catalog", exp.Identifier(this="automation_d", quoted=True))
                        table.set("db", exp.Identifier(this="silver", quoted=False))
                        table.set("this", exp.Identifier(this=snapshots.snapshot_name(table.name, "_dev"), quoted=True))
                rewritten = snapshots.replace_source_references(source, "automation_d", "_dev")
                self.assertEqual(expected, sqlglot.parse_one(rewritten, read="databricks"))
                self.assertFalse(any(snapshots.is_source(table) for table in sqlglot.parse_one(rewritten, read="databricks").find_all(exp.Table)))

    def test_column_collection_respects_alias_scope_and_quoted_names(self):
        planned = snapshots.collect_source_columns([
            "WITH scoped AS (SELECT source.`Order Key` FROM `synapse-prd`.pbi.dbx_fact_example source) "
            "SELECT source.`Customer Name` FROM `synapse-prd`.pbi.dbx_dim_example source JOIN scoped ON source.`Customer Key`=scoped.`Order Key`"
        ])
        by_name = {item["source_table"]: item["columns"] for item in planned}
        self.assertEqual(by_name["dbx_fact_example"], ["Order Key"])
        self.assertEqual(by_name["dbx_dim_example"], ["Customer Key", "Customer Name"])

    def test_star_preserves_all_columns_and_invalid_names_are_rejected(self):
        planned = snapshots.collect_source_columns(["SELECT * FROM `synapse-prd`.pbi.dbx_fact_example"])
        self.assertIsNone(planned[0]["columns"])
        with self.assertRaises(ValueError):
            snapshots.snapshot_name("dbx_fact_example`; DROP TABLE x")
        with self.assertRaises(ValueError):
            snapshots.snapshot_name("dbx_fact_example", "_prd")

    def test_manifest_rejects_unrelated_destinations_and_duplicate_sources(self):
        source = {"source_table": "dbx_fact_example", "snapshot_table": "SC_BI_industry_sales_src_dbx_fact_example", "columns": ["Order Key"]}
        self.assertEqual(snapshots.validate_manifest([source]), [source])
        for invalid in ([source, source], [dict(source, snapshot_table="unrelated_table")], [dict(source, columns=["key`evil"])]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                snapshots.validate_manifest(invalid)

    def test_incomplete_or_duplicate_receipts_cannot_publish(self):
        sources = [{"source_table": "dbx_fact_example", "snapshot_table": "SC_BI_industry_sales_src_dbx_fact_example", "columns": ["Order Key"]}]
        snapshots.validate_complete_receipts(sources, [{"source": "dbx_fact_example"}])
        for receipts in ([], [{"source": "unrelated"}], [{"source": "dbx_fact_example"}, {"source": "dbx_fact_example"}]):
            with self.subTest(receipts=receipts), self.assertRaises(ValueError):
                snapshots.validate_complete_receipts(sources, receipts)

    def test_pinned_snapshot_id_cannot_inject_sql(self):
        statement = snapshots.pinned_snapshot_query("raw", "a" * 32, ["Order Key"])
        self.assertIn("`Order Key`", statement)
        self.assertIn("'" + "a" * 32 + "'", statement)
        with self.assertRaises(ValueError):
            snapshots.pinned_snapshot_query("raw", "'; DROP TABLE x", ["Order Key"])

    def test_existing_wide_storage_allows_narrow_projection_without_type_changes(self):
        required = [("Order Key", "INT"), ("Net Value", "DECIMAL(18,3)")]
        stored = [("Order Key", "INT"), ("Unused Field", "STRING"), ("Net Value", "DECIMAL(18,3)")]
        self.assertEqual(snapshots.validate_storage_projection(required, stored), ["Unused Field"])
        for invalid in ([("Order Key", "INT")], [("Order Key", "STRING"), ("Net Value", "DECIMAL(18,3)")]):
            with self.subTest(stored=invalid), self.assertRaises(ValueError):
                snapshots.validate_storage_projection(required, invalid)

    def test_existing_view_is_altered_without_replacement_or_grant_changes(self):
        query = snapshots.snapshot_view_query("automation.bronze.raw", "automation.gold.state", ["Order Key"])
        existing = snapshots.snapshot_view_ddl("automation.silver.snapshot", query, True)
        self.assertTrue(existing.startswith("ALTER VIEW automation.silver.snapshot AS "))
        self.assertNotIn("REPLACE", existing)
        self.assertNotIn("DROP", existing)
        first = snapshots.snapshot_view_ddl("automation.silver.snapshot", query, False)
        self.assertTrue(first.startswith("CREATE VIEW "))
        self.assertIn("industry_sales.bundle", first)
        sqlglot.parse_one(existing, read="databricks")
        sqlglot.parse_one(first, read="databricks")


if __name__ == "__main__":
    unittest.main()