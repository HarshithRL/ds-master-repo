import ast
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from pyspark.sql import SparkSession


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from durable_results import cleanup_result_scratch, result_scratch_root, stage_result_frame


class DurableResultTests(unittest.TestCase):
    def test_write_failure_reports_actual_remote_plan_without_changing_error(self):
        spark = Mock()
        frame = Mock()
        frame.schema = Mock(fields=[])
        cause = RuntimeError("SQLServerException: Incorrect syntax near '-'")
        frame.write.mode.return_value.parquet.side_effect = cause
        frame.explain.side_effect = lambda **options: print('External engine query: SELECT "Date - Item Changed" FROM "PBI"."Orders-With-Hyphen"')
        emitted = StringIO()
        with tempfile.TemporaryDirectory() as directory:
            with redirect_stdout(emitted):
                with self.assertRaises(RuntimeError) as failure:
                    stage_result_frame(spark, frame, Path(directory) / "stage")
            receipt = json.loads(emitted.getvalue())
            diagnostics = json.loads(Path(receipt["diagnostics_path"]).read_text())
        self.assertIs(failure.exception, cause)
        self.assertEqual(receipt["stage"], "scratch_write_failed")
        self.assertIn("SQLServerException", receipt["error"])
        self.assertIn('FROM "PBI"."Orders-With-Hyphen"', diagnostics["physical_plan"])
        self.assertNotIn("physical_plan", receipt)
        frame.explain.assert_called_once_with(mode="formatted")
        self.assertEqual(spark.conf.set.call_count, 4)

    def test_plan_diagnostic_failure_does_not_mask_original_write_error(self):
        spark = Mock()
        frame = Mock()
        frame.schema = Mock(fields=[])
        cause = RuntimeError("Original JDBC parse failure")
        frame.write.mode.return_value.parquet.side_effect = cause
        frame.explain.side_effect = ValueError("Plan unavailable")
        emitted = StringIO()
        with tempfile.TemporaryDirectory() as directory:
            with redirect_stdout(emitted):
                with self.assertRaises(RuntimeError) as failure:
                    stage_result_frame(spark, frame, Path(directory) / "stage")
            diagnostics = json.loads(Path(json.loads(emitted.getvalue())["diagnostics_path"]).read_text())
        self.assertIs(failure.exception, cause)
        self.assertEqual(diagnostics["plan_error"], "ValueError: Plan unavailable")
        self.assertEqual(spark.conf.set.call_count, 4)

    def test_large_logs_are_bounded_but_full_diagnostics_and_failure_are_preserved(self):
        spark = Mock()
        frame = Mock()
        frame.schema = Mock(fields=[])
        cause = RuntimeError("\U0001f600" * 20000)
        frame.write.mode.return_value.parquet.side_effect = cause
        plan = "External engine query: " + "SQL " * 50000
        frame.explain.side_effect = lambda **options: print(plan)
        emitted = StringIO()
        with tempfile.TemporaryDirectory() as directory:
            with redirect_stdout(emitted):
                with self.assertRaises(RuntimeError) as failure:
                    stage_result_frame(spark, frame, Path(directory) / "stage")
            receipt = json.loads(emitted.getvalue())
            diagnostics = json.loads(Path(receipt["diagnostics_path"]).read_text())
            self.assertEqual(diagnostics["error"], str(cause))
            self.assertEqual(diagnostics["physical_plan"], plan + "\n")
        self.assertIs(failure.exception, cause)
        self.assertLessEqual(len(emitted.getvalue().encode("utf-8")), 8193)

    def test_diagnostic_file_error_cannot_hide_original_failure(self):
        spark = Mock()
        frame = Mock()
        frame.schema = Mock(fields=[])
        cause = RuntimeError("Original JDBC failure")
        frame.write.mode.return_value.parquet.side_effect = cause
        emitted = StringIO()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(Path, "open", side_effect=PermissionError("diagnostic write denied")), redirect_stdout(emitted):
                with self.assertRaises(RuntimeError) as failure:
                    stage_result_frame(spark, frame, Path(directory) / "stage")
        self.assertIs(failure.exception, cause)
        self.assertIn("PermissionError", json.loads(emitted.getvalue())["diagnostics_error"])

    def test_staging_mode_serializes_with_real_spark_connect_writer(self):
        from pyspark.sql.connect import proto
        from pyspark.sql.connect.plan import Range, WriteOperation

        spark = Mock()
        frame = Mock()
        schema = Mock(fields=[])
        frame.schema = schema
        stored = spark.read.schema.return_value.option.return_value.option.return_value.parquet.return_value
        stored.schema = schema
        self.assertIs(stage_result_frame(spark, frame, "/Volumes/example/stage"), stored)
        mode = frame.write.mode.call_args.args[0]
        operation = WriteOperation(Range(0, 1, 1, None))
        operation.mode = mode
        self.assertEqual(operation.command(Mock()).write_operation.mode, proto.WriteOperation.SaveMode.SAVE_MODE_ERROR_IF_EXISTS)
        operation.mode = "errorifexists"
        with self.assertRaises(ValueError):
            operation.command(Mock())

    def test_preflight_preserves_real_error_instead_of_claiming_missing_grants(self):
        runtime = ROOT / "src/notebooks/materialize_dashboard_results.py"
        tree = ast.parse(runtime.read_text())
        preflight = next(statement for statement in tree.body if isinstance(statement, ast.Try))
        cause = ValueError("Unsupported writer save mode")
        environment = {"scratch": MagicMock(), "stage_result_frame": Mock(side_effect=cause), "spark": Mock(), "cleanup_result_scratch": Mock()}
        with self.assertRaises(RuntimeError) as failure:
            exec(compile(ast.Module(body=[preflight], type_ignores=[]), str(runtime), "exec"), environment)
        self.assertIs(failure.exception.__cause__, cause)
        self.assertIn("ValueError: Unsupported writer save mode", str(failure.exception))
        self.assertNotIn("requires READ_VOLUME", str(failure.exception))

    def test_scratch_paths_are_batch_and_target_scoped_in_existing_volume(self):
        batch = "a" * 32
        for target, catalog in (("D", "automation_d"), ("T", "automation_d"), ("A", "automation_a"), ("P", "automation_p")):
            self.assertEqual(str(result_scratch_root(catalog, target, batch)), f"/Volumes/{catalog}/bronze/bronze_volume/SC_BI_industry_sales_result_scratch/{target}/{batch}")
        for catalog, target, batch_id in (("automation_p", "D", batch), ("synapse-prd", "P", batch), ("automation_d", "../", batch), ("automation_d", "D", "../other")):
            with self.subTest(catalog=catalog, target=target, batch=batch_id), self.assertRaises(ValueError):
                result_scratch_root(catalog, target, batch_id)

    def test_durable_rows_survive_lost_local_checkpoint_and_keep_native_values(self):
        spark = SparkSession.builder.master("local[2]").appName("durable-result-recovery").config("spark.sql.shuffle.partitions", "2").getOrCreate()
        spark.sparkContext.setLogLevel("ERROR")
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "checkpoint"
                expected = spark.sql("SELECT * FROM VALUES (1,12.125BD,DATE '1970-01-01',TIMESTAMP '2026-10-15 10:34:55.123456','name with space'),(1,12.125BD,DATE '1970-01-01',TIMESTAMP '2026-10-15 10:34:55.123456','name with space'),(2,CAST(NULL AS DECIMAL(8,3)),DATE '1500-01-01',TIMESTAMP '1500-01-01 00:00:00',CAST(NULL AS STRING)) AS source(`Native Key`,quantity,source_date,source_timestamp,label)")
                settings = {name: spark.conf.get(name) for name in ("spark.sql.parquet.datetimeRebaseModeInWrite", "spark.sql.parquet.int96RebaseModeInWrite")}
                local = expected.localCheckpoint(eager=True)
                durable = stage_result_frame(spark, local, path)
                self.assertEqual({name: spark.conf.get(name) for name in settings}, settings)
                local.unpersist(blocking=True)
                cached = spark.sparkContext._jsc.sc().getPersistentRDDs().values().iterator()
                while cached.hasNext():
                    cached.next().unpersist(True)
                with self.assertRaises(Exception) as lost:
                    local.count()
                self.assertIn("Checkpoint block", str(lost.exception))
                spark.catalog.clearCache()
                self.assertEqual(durable.count(), 3)
                self.assertEqual(durable.exceptAll(expected).count(), 0)
                self.assertEqual(expected.exceptAll(durable).count(), 0)
                self.assertEqual(durable.columns, expected.columns)
                empty_path = Path(directory) / "empty"
                empty = stage_result_frame(spark, expected.limit(0), empty_path)
                self.assertEqual(empty.count(), 0)
                with self.assertRaises(Exception):
                    stage_result_frame(spark, expected, path)
                self.assertEqual({name: spark.conf.get(name) for name in settings}, settings)
                cleanup_result_scratch(path)
                self.assertFalse(path.exists())
                self.assertTrue(empty_path.exists())
        finally:
            spark.stop()


if __name__ == "__main__":
    unittest.main()