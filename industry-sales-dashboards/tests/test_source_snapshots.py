import importlib.util
import json
import unittest
from pathlib import Path

import sqlglot
from sqlglot import exp


ROOT = Path(__file__).resolve().parents[1]
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
        source = {"source_table": "dbx_fact_example", "snapshot_table": "industry_sales_src_dbx_fact_example", "columns": ["Order Key"]}
        self.assertEqual(snapshots.validate_manifest([source]), [source])
        for invalid in ([source, source], [dict(source, snapshot_table="unrelated_table")], [dict(source, columns=["key`evil"])]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                snapshots.validate_manifest(invalid)

    def test_incomplete_or_duplicate_receipts_cannot_publish(self):
        sources = [{"source_table": "dbx_fact_example", "snapshot_table": "industry_sales_src_dbx_fact_example", "columns": ["Order Key"]}]
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


if __name__ == "__main__":
    unittest.main()