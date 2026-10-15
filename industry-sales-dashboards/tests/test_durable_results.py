import sys
import tempfile
import unittest
from pathlib import Path

from pyspark.sql import SparkSession


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from durable_results import cleanup_result_scratch, result_scratch_root, stage_result_frame


class DurableResultTests(unittest.TestCase):
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