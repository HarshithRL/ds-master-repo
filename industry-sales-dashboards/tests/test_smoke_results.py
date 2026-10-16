import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import smoke_results as smoke


class SmokeResultTests(unittest.TestCase):
    def test_schema_analysis_cannot_fall_back_to_an_unreplaced_foreign_table(self):
        spark = Mock()
        plan = {"source_sql": "SELECT value FROM foreign_catalog.schema.real_table", "consumer_sql": "SELECT 1", "producers": []}
        with self.assertRaises(ValueError):
            smoke.check_dataset_contract(spark, plan, {}, date(2026, 10, 15))
        spark.sql.assert_not_called()

    def test_real_source_roundtrips_and_all_schema_checks_complete_without_production_writes(self):
        from pyspark.sql import SparkSession
        from dataset_results import compile_dataset, table_edits

        spark = SparkSession.builder.master("local[2]").appName("bounded-smoke-gate").config("spark.sql.shuffle.partitions", "2").getOrCreate()
        spark.sparkContext.setLogLevel("ERROR")
        try:
            spark.sql("SELECT * FROM VALUES ('O1',12.125BD,'YOR','C',1),('O2',7.75BD,'YOR','C',1) AS source(`Order Number`,`Net Value Euro`,`Document Type`,`Rejection Status`,`FK Sales Organization`)").createOrReplaceTempView("fixture_smoke_orders")
            spark.sql("SELECT * FROM VALUES (1,'BE'),(2,'DE') AS source(source_key,country)").createOrReplaceTempView("fixture_smoke_lookup")
            source = "SELECT o.`Order Number` AS order_id, o.`Net Value Euro` AS value_eur FROM `synapse-prd`.pbi.`" + smoke.REMOTE_ORDER_TABLE + "` o WHERE o.`Document Type`='YOR' AND o.`Rejection Status`='C' AND o.`FK Sales Organization` IS NOT NULL"
            plans = [compile_dataset("open_orders", "ds_smoke_" + str(index), source, {}) for index in range(17)]
            plans.append(compile_dataset("quotations", "ds_smoke_lookup", "SELECT source_key, country FROM `synapse-prd`.pbi.dbx_dim_example", {}))
            replacements = {"synapse-prd.pbi." + smoke.REMOTE_ORDER_TABLE: "fixture_smoke_orders", "synapse-prd.pbi.dbx_dim_example": "fixture_smoke_lookup"}
            schemas = {smoke.REMOTE_ORDER_TABLE: ["Order Number", "Net Value Euro", "Document Type", "Rejection Status", "FK Sales Organization"], "dbx_dim_example": ["source_key", "country"]}
            mapping = json.loads((ROOT / "src/config/cs_team_sales_org_mapping.json").read_text())["rows"]
            proxy = Mock(wraps=spark)
            proxy.sql.side_effect = lambda query: spark.sql(table_edits(query, replacements))

            def warehouse_probe(session, workspace, warehouse_id, query, path, timeout_seconds):
                self.assertEqual(timeout_seconds, 120)
                return smoke.stage_result_frame(spark, spark.sql(table_edits(query, replacements)), path)

            log = Mock()
            with tempfile.TemporaryDirectory() as directory:
                scratch = Path(directory) / "own-batch"
                scratch.mkdir()
                with patch.object(smoke, "preflight_cancellation_warehouse"), patch.object(smoke, "stage_cancellation_warehouse", side_effect=warehouse_probe) as stage:
                    smoke.run_smoke_checks(proxy, Mock(), "69ada62b2fb9b9e2", plans, schemas, mapping, "synapse-prd", scratch, "7181820732839861", log)
                self.assertFalse(scratch.exists())
                stage.assert_called_once()
                verified = [call for call in log.call_args_list if call.args[0] == "smoke_source_verified"]
                self.assertEqual(len(verified), 2)
                self.assertTrue(all(call.kwargs["rows"] <= 1 for call in verified))
                self.assertEqual(sum(call.args[0] == "smoke_dataset_verified" for call in log.call_args_list), 18)
                self.assertEqual(log.call_args_list[-1].args[0], "smoke_checks_passed")
                self.assertFalse(any(call.args[0].lstrip().upper().startswith(("CREATE ", "INSERT ", "DELETE ", "ALTER ", "DROP ")) for call in proxy.sql.call_args_list))
                scratch.mkdir()
                log.reset_mock()
                with patch.object(smoke, "preflight_cancellation_warehouse"), patch.object(smoke, "stage_cancellation_warehouse", side_effect=warehouse_probe), patch.object(smoke, "check_dataset_contract", side_effect=ValueError("bad dataset schema")):
                    with self.assertRaises(ValueError):
                        smoke.run_smoke_checks(proxy, Mock(), "69ada62b2fb9b9e2", plans, schemas, mapping, "synapse-prd", scratch, "7181820732839861", log)
                self.assertTrue(scratch.exists())
                self.assertFalse(any(call.args[0] == "smoke_checks_passed" for call in log.call_args_list))
        finally:
            spark.stop()

    def test_all_active_sources_have_explicit_one_row_probes(self):
        plans = json.loads((ROOT / "src/config/dashboard_results.json").read_text())["datasets"]
        schemas = json.loads((ROOT / "src/config/source_column_names.json").read_text())
        sources = smoke.collect_source_columns([plan["source_sql"] for plan in plans], schemas)
        self.assertEqual(len(sources), 14)
        for source in sources:
            source["columns"] = source["columns"] or schemas[source["source_table"]]
            query = smoke.source_probe_sql(source, "synapse-prd")
            self.assertTrue(query.endswith(" LIMIT 1"))
            self.assertNotIn("SELECT *", query)
            self.assertIn("`synapse-prd`.`pbi`.`" + source["source_table"] + "`", query)
        with self.assertRaises(ValueError):
            smoke.source_probe_sql({"source_table": "example", "columns": None}, "synapse-prd")

    def test_failed_early_warehouse_gate_cannot_start_sources_or_dataset_work(self):
        plans = json.loads((ROOT / "src/config/dashboard_results.json").read_text())["datasets"]
        schemas = json.loads((ROOT / "src/config/source_column_names.json").read_text())
        spark = Mock()
        spark.sql.return_value.first.return_value = {"job_identity": "run-sp", "business_date": "2026-10-15"}
        cause = RuntimeError("Warehouse access denied")
        with patch.object(smoke, "preflight_cancellation_warehouse", side_effect=cause), patch.object(smoke, "stage_cancellation_warehouse") as stage, patch.object(smoke, "check_dataset_contract") as contracts:
            with self.assertRaises(RuntimeError) as failure:
                smoke.run_smoke_checks(spark, Mock(), "69ada62b2fb9b9e2", plans, schemas, [], "synapse-prd", Path("/unused"), "7181820732839861", Mock())
        self.assertIs(failure.exception, cause)
        stage.assert_not_called()
        contracts.assert_not_called()
        spark.createDataFrame.assert_not_called()


if __name__ == "__main__":
    unittest.main()