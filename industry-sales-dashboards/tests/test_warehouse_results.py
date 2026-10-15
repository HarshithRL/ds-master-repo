import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import warehouse_results as warehouse


def response(state="SUCCEEDED", rows=None):
    return SimpleNamespace(statement_id="own-statement", status=SimpleNamespace(state=SimpleNamespace(value=state), error=None), manifest=SimpleNamespace(truncated=False), result=SimpleNamespace(data_array=rows or [], next_chunk_index=None))


class WarehouseResultTests(unittest.TestCase):
    def test_exact_native_failure_is_rejected_and_quoted_forms_pass(self):
        failing = 'External engine query: SELECT "Date - Item Changed" FROM pbi.dbx_fact_o2c_-_self_service_-_sales_orders WHERE "Rejection Status"=\'C\''
        with self.assertRaises(ValueError):
            warehouse.validate_quoted_order_scan(failing)
        for remote in ('"PBI"."DBX_Fact_O2C_-_Self_Service_-_Sales_Orders"', '[PBI].[DBX_Fact_O2C_-_Self_Service_-_Sales_Orders]'):
            warehouse.validate_quoted_order_scan(failing.replace("pbi." + warehouse.REMOTE_ORDER_TABLE, remote))
        with self.assertRaises(ValueError):
            warehouse.validate_quoted_order_scan("No remote SQL")

    def test_cancellation_runs_first_without_losing_or_reordering_other_plans(self):
        plans = [{"dashboard": "open_orders", "dataset": "first"}, {"dashboard": "open_orders", "dataset": warehouse.CANCELLATION_DATASET}, {"dashboard": "quotations", "dataset": "ds_quotations"}]
        self.assertEqual(warehouse.prioritize_cancellation(plans), [plans[1], plans[0], plans[2]])
        self.assertEqual(plans[0]["dataset"], "first")

    def test_sql_output_path_cannot_overwrite_shared_or_other_batch_data(self):
        path = "/Volumes/automation_a/bronze/bronze_volume/SC_BI_industry_sales_result_scratch/A/" + "a" * 32 + "/open_orders/ds_cancellations_detail_7d/0"
        query = "SELECT 12.125 AS __input_0"
        self.assertEqual(warehouse.warehouse_stage_sql(query, path), f"INSERT OVERWRITE DIRECTORY '{path}' USING PARQUET\n" + query)
        for invalid in ("/Volumes/automation_a/bronze/bronze_volume", path + "/../1", path.replace("ds_cancellations_detail_7d", "other"), path.replace("automation_a", "synapse-prd"), path.replace("automation_a", "automation_p")):
            with self.subTest(path=invalid), self.assertRaises(ValueError):
                warehouse.warehouse_stage_sql(query, invalid)

    def test_preflight_requires_same_workspace_identity_and_quoted_native_plan(self):
        workspace = Mock()
        workspace.config.host = "https://adb-4796304964978539.19.azuredatabricks.net"
        workspace.statement_execution.execute_statement.side_effect = [response(rows=[["run-sp"]]), response(rows=[['External engine query: SELECT "x" FROM "PBI"."DBX_Fact_O2C_-_Self_Service_-_Sales_Orders"']])]
        warehouse.preflight_cancellation_warehouse(workspace, "0ef3e37fbbd5b772", "SELECT source", "run-sp", "4796304964978539")
        self.assertEqual(workspace.statement_execution.execute_statement.call_count, 2)
        workspace.statement_execution.execute_statement.side_effect = [response(rows=[["different-sp"]])]
        with self.assertRaises(ValueError) as mismatch:
            warehouse.preflight_cancellation_warehouse(workspace, "0ef3e37fbbd5b772", "SELECT source", "run-sp", "4796304964978539")
        self.assertIn("different-sp", str(mismatch.exception))
        self.assertIn("run-sp", str(mismatch.exception))
        workspace.config.host = "https://adb-4844910598668398.18.azuredatabricks.net"
        with self.assertRaises(ValueError):
            warehouse.preflight_cancellation_warehouse(workspace, "0ef3e37fbbd5b772", "SELECT source", "run-sp", "4796304964978539")

    def test_timeout_cancels_only_the_submitted_statement_and_failure_cannot_succeed(self):
        workspace = Mock()
        workspace.statement_execution.execute_statement.return_value = response("RUNNING")
        with patch.object(warehouse, "monotonic", side_effect=[0, 61]):
            with self.assertRaises(TimeoutError):
                warehouse.execute_warehouse_statement(workspace, "0ef3e37fbbd5b772", "SELECT source", 60)
        workspace.statement_execution.cancel_execution.assert_called_once_with("own-statement")
        workspace.statement_execution.execute_statement.return_value = response("FAILED")
        with self.assertRaises(RuntimeError):
            warehouse.execute_warehouse_statement(workspace, "0ef3e37fbbd5b772", "SELECT source")
        workspace.statement_execution.execute_statement.return_value = response()
        workspace.statement_execution.execute_statement.return_value.manifest.truncated = True
        with self.assertRaises(ValueError):
            warehouse.execute_warehouse_statement(workspace, "0ef3e37fbbd5b772", "SELECT source")

    def test_status_network_failure_still_cancels_only_own_statement(self):
        workspace = Mock()
        workspace.statement_execution.execute_statement.return_value = response("RUNNING")
        error = ConnectionError("status fetch failed")
        workspace.statement_execution.get_statement.side_effect = error
        with patch.object(warehouse, "sleep"):
            with self.assertRaises(ConnectionError) as failure:
                warehouse.execute_warehouse_statement(workspace, "0ef3e37fbbd5b772", "SELECT source")
        self.assertIs(failure.exception, error)
        workspace.statement_execution.cancel_execution.assert_called_once_with("own-statement")

    def test_actual_producer_routes_cancellation_only_to_warehouse_and_keeps_failed_scratch(self):
        runtime = ROOT / "src/notebooks/materialize_dashboard_results.py"
        tree = ast.parse(runtime.read_text())
        loop = next(statement for statement in tree.body if isinstance(statement, ast.For) and isinstance(statement.iter, ast.Name) and statement.iter.id == "plans")
        compiled = compile(ast.Module(body=[loop], type_ignores=[]), str(runtime), "exec")
        plan = next(item for item in json.loads((ROOT / "src/config/dashboard_results.json").read_text())["datasets"] if warehouse.is_cancellation_plan(item))
        source = plan["producers"][0]["sql"]
        stage = Mock()
        client = Mock()
        store = Mock()
        cleanup = Mock()
        spark = Mock()
        from datetime import date
        from allocation_stages import freeze_sql_date
        from durable_results import result_dataset_scratch

        with tempfile.TemporaryDirectory() as directory:
            environment = {"spark": spark, "plans": [plan], "scratch": Path(directory), "verified_results": {}, "log": Mock(), "is_cancellation_plan": warehouse.is_cancellation_plan, "workspace": client, "args": SimpleNamespace(warehouse_id="69ada62b2fb9b9e2"), "stage_cancellation_warehouse": stage, "stage_result_frame": Mock(side_effect=AssertionError("Broken cluster JDBC route must never execute cancellation")), "freeze_sql_date": freeze_sql_date, "resolve": lambda sql: sql, "business_date": date(2026, 10, 15), "result_dataset_scratch": result_dataset_scratch, "cleanup_result_scratch": cleanup, "store_result": store}
            exec(compiled, environment)
            stage.assert_called_once_with(spark, client, "69ada62b2fb9b9e2", freeze_sql_date(source, date(2026, 10, 15)), Path(directory) / "open_orders" / warehouse.CANCELLATION_DATASET / "0")
            store.assert_called_once_with(plan["producers"][0]["table"], stage.return_value, plan)
            cleanup.assert_called_once()
            stage.reset_mock()
            cleanup.reset_mock()
            store.reset_mock()
            stage.side_effect = RuntimeError("Warehouse failed")
            with self.assertRaises(RuntimeError):
                exec(compiled, environment)
            cleanup.assert_not_called()
            store.assert_not_called()
        self.assertLess(runtime.read_text().index("plans = prioritize_cancellation(plans)"), runtime.read_text().index("for plan in plans:"))
        self.assertLess(runtime.read_text().index("preflight_cancellation_warehouse(workspace"), runtime.read_text().index("check_owned(state)"))


if __name__ == "__main__":
    unittest.main()