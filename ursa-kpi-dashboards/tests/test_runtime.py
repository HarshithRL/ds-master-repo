import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ursa_runtime import MARKER, check_owned, cleanup_scratch, execute, load_plan, publish_state, scratch_root, source_projection, stage_frame, validate_columns, validate_consumer_schema, validate_receipts, validate_schema, view_ddl, view_query


class RuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = load_plan(ROOT / "src" / "config")

    def test_source_plan_is_bounded_to_exactly_fifteen_relations_and_eighty_one_columns(self):
        self.assertEqual(len(self.plan["sources"]), 15)
        self.assertEqual(sum(len(source["columns"]) for source in self.plan["sources"]), 81)
        for source in self.plan["sources"]:
            statement = source_projection(source)
            self.assertNotIn("*", statement)
            self.assertIn("`synapse-prd`.`pbi`", statement)
            self.assertNotIn("CREATE", statement)

    def test_wrong_environment_is_rejected_before_any_sql_or_write(self):
        spark = Mock()
        spark.conf.get.return_value = "4796304964978539"
        with self.assertRaises(ValueError):
            execute(spark, ROOT / "src" / "config", "automation_d", "synapse-prd", "D", "materialize")
        spark.sql.assert_not_called()
        spark.createDataFrame.assert_not_called()

    def test_gold_views_publish_only_the_active_batch_with_explicit_columns(self):
        query = view_query("raw", "state", ["KPI Name", "value"])
        self.assertEqual(query, f"SELECT `KPI Name`, `value` FROM raw WHERE `{MARKER}` = (SELECT snapshot_id FROM state)")
        self.assertTrue(view_ddl("view", query, True).startswith("ALTER VIEW"))
        self.assertNotIn("REPLACE", view_ddl("view", query, True))
        self.assertIn("'ursa_kpi.bundle'='ursa-kpi-dashboards'", view_ddl("view", query, False))

    def test_missing_duplicate_or_unverified_receipts_cannot_change_the_state(self):
        receipts = [{"dataset": dataset["dataset"], "rows": 1, "columns": ["value"], "verified": True} for dataset in self.plan["datasets"]]
        validate_receipts(self.plan, receipts)
        unverified = copy.deepcopy(receipts)
        unverified[0]["verified"] = False
        for invalid in (receipts[:-1], receipts + receipts[:1], unverified):
            spark = Mock()
            with self.assertRaises(ValueError):
                publish_state(spark, self.plan, "state", "f" * 32, None, invalid)
            spark.sql.assert_not_called()
            spark.createDataFrame.assert_not_called()

    def test_empty_known_populations_are_not_vacuously_verified(self):
        receipts = [{"dataset": dataset["dataset"], "rows": 1, "columns": ["value"], "verified": True} for dataset in self.plan["datasets"]]
        next(receipt for receipt in receipts if receipt["dataset"] == "test_invoiced_value")["rows"] = 0
        validate_receipts(self.plan, receipts)
        receipts[0]["rows"] = 0
        with self.assertRaises(ValueError):
            validate_receipts(self.plan, receipts)

    def test_native_consumer_analysis_is_required_against_the_staged_result(self):
        frame = Mock()
        frame.columns = ["value"]
        spark = Mock()
        spark.sql.return_value.columns = ["value"]
        dataset = {"dataset": "test", "consumer_sql": "SELECT * FROM `${var.catalog}`.gold.`URSA_KPI_result_test${var.result_suffix}` ORDER BY missing"}
        validate_consumer_schema(spark, dataset, frame)
        self.assertIn("URSA_KPI_preview_result", spark.sql.call_args.args[0])
        self.assertIn("ORDER BY missing", spark.sql.call_args.args[0])
        spark.sql.return_value.limit.assert_called_once_with(0)
        spark.sql.side_effect = ValueError("Unresolved ORDER BY column")
        with self.assertRaises(ValueError):
            validate_consumer_schema(spark, dataset, frame)

    def test_publication_preserves_state_table_identity_and_grants(self):
        receipts = [{"dataset": dataset["dataset"], "rows": 1, "columns": ["value"], "verified": True} for dataset in self.plan["datasets"]]
        spark = Mock()
        publish_state(spark, self.plan, "state", "f" * 32, None, receipts)
        self.assertTrue(spark.sql.call_args.args[0].startswith("INSERT OVERWRITE TABLE state"))
        self.assertNotIn("REPLACE", spark.sql.call_args.args[0])

    def test_scratch_is_isolated_and_cleanup_cannot_escape_it(self):
        batch = "a" * 32
        self.assertEqual(str(scratch_root("automation_d", "D", batch)), f"/Volumes/automation_d/bronze/bronze_volume/URSA_KPI/D/{batch}")
        for catalog, target, value in (("automation_p", "D", batch), ("automation_d", "D", "../other")):
            with self.assertRaises(ValueError):
                scratch_root(catalog, target, value)
        with self.assertRaises(ValueError):
            cleanup_scratch("/Volumes/automation_d/bronze/bronze_volume", "automation_d", "D", batch)
        with self.assertRaises(ValueError):
            cleanup_scratch(scratch_root("automation_d", "D", batch) / "..", "automation_d", "D", batch)

    def test_durable_staging_uses_connect_compatible_no_overwrite_mode(self):
        field = SimpleNamespace(name="value", dataType="native_type")
        frame = Mock()
        frame.schema = SimpleNamespace(fields=[field])
        stored = Mock()
        stored.schema = frame.schema
        spark = Mock()
        spark.read.schema.return_value.parquet.return_value = stored
        result = stage_frame(spark, frame, "/isolated/dataset")
        self.assertIs(result, stored)
        frame.write.mode.assert_called_once_with("error")
        frame.write.mode.return_value.parquet.assert_called_once_with("/isolated/dataset")
        spark.read.schema.assert_called_once_with(frame.schema)

    def test_schema_drift_and_reserved_or_duplicate_columns_are_rejected(self):
        validate_schema([("value", "int")], [("value", "int")])
        with self.assertRaises(ValueError):
            validate_schema([("value", "int")], [("value", "double")])
        for columns in ([], ["value", "Value"], [MARKER], [MARKER.upper()], ["bad`name"]):
            with self.assertRaises(ValueError):
                validate_columns(columns)

    def test_existing_foreign_owned_objects_are_not_modified(self):
        spark = Mock()
        spark.catalog.tableExists.return_value = True
        spark.catalog.getTable.return_value.tableType = "VIEW"
        spark.sql.return_value.collect.return_value = [{"key": "ursa_kpi.bundle", "value": "another-bundle"}]
        with self.assertRaises(ValueError):
            check_owned(spark, "name", "VIEW")
        spark.catalog.getTable.return_value.tableType = "MANAGED"
        with self.assertRaises(ValueError):
            check_owned(spark, "name", "VIEW")


if __name__ == "__main__":
    unittest.main()