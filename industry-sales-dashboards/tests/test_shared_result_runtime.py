import ast
import sys
import tempfile
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from unittest.mock import Mock

from pyspark.sql import SparkSession, functions as sql_functions


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from allocation_stages import freeze_sql_date, query_parts
from dataset_results import result_name, result_storage_name, unique_result_producers, validate_result_receipts
from durable_results import cleanup_result_scratch, result_dataset_scratch, stage_result_frame
from source_snapshots import quote_column
from warehouse_results import is_cancellation_plan


class SharedResultRuntimeTests(unittest.TestCase):
    def test_actual_producer_loop_computes_once_and_reuses_only_verified_current_batch(self):
        spark = SparkSession.builder.master("local[2]").appName("shared-result-publication").config("spark.sql.shuffle.partitions", "2").getOrCreate()
        spark.sparkContext.setLogLevel("ERROR")
        scratch_directory = tempfile.TemporaryDirectory()
        scratch = Path(scratch_directory.name)
        marker = "__industry_snapshot_id"
        batch = "new_batch"
        shared = result_name("quotations", "shared", "converted")
        source = "SELECT quote_number FROM `synapse-prd`.pbi.dbx_conversion_fixture"
        plans = [{"dashboard": "quotations", "dataset": dataset, "mode": "filtered", "producers": [
            {"component": "converted", "table": shared, "shared": True, "sql": source},
            {"component": "result", "table": result_name("quotations", dataset), "sql": "SELECT quote_number FROM converted"},
        ]} for dataset in ("ds_quotations", "ds_quotations_detail", "ds_expiring_quotes")]
        writes = []
        outputs = {}
        receipts = []
        verified_results = {}

        def relation(table, layer="gold"):
            return "fixture_" + layer + "_" + table

        def store_result(table, frame, plan):
            writes.append(table)
            outputs[table] = frame.collect()
            captured = spark.createDataFrame(outputs[table], frame.schema).withColumn(marker, sql_functions.lit(batch))
            previous = spark.sql("SELECT 'previous_only' AS quote_number").withColumn(marker, sql_functions.lit("old_batch"))
            captured.unionByName(previous).createOrReplaceTempView(relation(result_storage_name(table), "silver"))
            receipt = {"dashboard": plan["dashboard"], "dataset": plan["dataset"], "table": table, "rows": len(outputs[table]), "columns": frame.columns}
            receipts.append(receipt)
            verified_results[table] = receipt

        try:
            spark.sql("SELECT * FROM VALUES ('Q1'),('Q1'),(CAST(NULL AS STRING)) AS source(quote_number)").createOrReplaceTempView("fixture_conversion")
            unique_result_producers(plans)
            runtime_path = ROOT / "src/notebooks/materialize_dashboard_results.py"
            tree = ast.parse(runtime_path.read_text())
            loop = next(statement for statement in tree.body if isinstance(statement, ast.For) and isinstance(statement.iter, ast.Name) and statement.iter.id == "plans")
            proxy = Mock(wraps=spark)
            logs = Mock()
            self.assertNotIn("localCheckpoint", runtime_path.read_text())
            environment = {"spark": proxy, "plans": plans, "batch": batch, "marker": marker, "business_date": date(2026, 10, 14), "receipts": receipts, "verified_results": verified_results, "relation": relation, "store_result": store_result, "resolve": lambda statement: statement.replace("`synapse-prd`.pbi.dbx_conversion_fixture", "fixture_conversion"), "log": logs, "sql_functions": sql_functions, "quote_column": quote_column, "result_storage_name": result_storage_name, "freeze_sql_date": freeze_sql_date, "query_parts": query_parts, "scratch": scratch, "stage_result_frame": stage_result_frame, "result_dataset_scratch": result_dataset_scratch, "cleanup_result_scratch": cleanup_result_scratch, "is_cancellation_plan": is_cancellation_plan}
            exec(compile(ast.Module(body=[loop], type_ignores=[]), str(runtime_path), "exec"), environment)
            self.assertEqual(writes.count(shared), 1)
            self.assertEqual(sum(call.args == ("SELECT quote_number FROM fixture_conversion",) for call in proxy.sql.call_args_list), 1)
            self.assertEqual(sum(call.args[0] == "result_reused" for call in logs.call_args_list), 2)
            self.assertEqual(len(receipts), 6)
            self.assertEqual(list(scratch.glob("*/*")), [])
            for plan in plans:
                self.assertEqual(Counter(outputs[result_name("quotations", plan["dataset"])]), Counter(outputs[shared]))
                self.assertEqual(len(outputs[result_name("quotations", plan["dataset"])]), 3)
            extra = [{"dashboard": "open_orders", "dataset": "fixture_" + str(index), "producers": [{"table": "fixture_" + str(index), "sql": "SELECT 1"}]} for index in range(14)]
            extra_receipts = [{"dashboard": plan["dashboard"], "dataset": plan["dataset"], "table": plan["producers"][0]["table"]} for plan in extra]
            validate_result_receipts(plans + extra, receipts + extra_receipts)
            with self.assertRaises(ValueError):
                validate_result_receipts(plans + extra, receipts[:-1] + extra_receipts)
        finally:
            spark.stop()
            scratch_directory.cleanup()


if __name__ == "__main__":
    unittest.main()