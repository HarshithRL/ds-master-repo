import importlib.util
import unittest
from pathlib import Path

from pyspark.sql import SparkSession


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("snapshot_view_runtime", ROOT / "src/source_snapshots.py")
snapshots = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshots)


class SourceSnapshotRuntimeTests(unittest.TestCase):
    def test_narrow_batch_retains_native_values_inside_existing_wide_schema(self):
        spark = SparkSession.builder.master("local[2]").appName("snapshot-storage-compatibility").config("spark.sql.shuffle.partitions", "2").getOrCreate()
        spark.sparkContext.setLogLevel("ERROR")
        try:
            frame = spark.sql("SELECT * FROM VALUES (1,12.125BD,'new'),(1,12.125BD,'new'),(2,CAST(NULL AS DECIMAL(8,3)),'new') AS source(`Order Key`,quantity,__industry_snapshot_id)")
            stored = spark.sql("SELECT CAST(NULL AS STRING) AS `Unused Field`, CAST(NULL AS DECIMAL(8,3)) AS quantity, CAST(NULL AS INT) AS `Order Key`, CAST(NULL AS STRING) AS __industry_snapshot_id").schema
            aligned = snapshots.align_storage_rows(frame, stored)
            self.assertEqual(aligned.columns, ["Unused Field", "quantity", "Order Key", "__industry_snapshot_id"])
            self.assertEqual(aligned.count(), 3)
            self.assertEqual(aligned.where("`Unused Field` IS NOT NULL").count(), 0)
            selected = aligned.select("`Order Key`", "quantity", "__industry_snapshot_id")
            self.assertEqual(frame.exceptAll(selected).count(), 0)
            self.assertEqual(selected.exceptAll(frame).count(), 0)
            self.assertEqual(aligned.schema["Unused Field"].dataType, stored["Unused Field"].dataType)
        finally:
            spark.stop()

    def test_unpublished_partial_batch_does_not_replace_visible_rows(self):
        spark = SparkSession.builder.master("local[2]").appName("source-snapshot-publication").config("spark.sql.shuffle.partitions", "2").getOrCreate()
        spark.sparkContext.setLogLevel("ERROR")
        try:
            spark.sql("SELECT 'old' AS snapshot_id").createOrReplaceTempView("fixture_state")
            old_id = "a" * 32
            new_id = "b" * 32
            spark.sql(f"SELECT '{old_id}' AS snapshot_id").createOrReplaceTempView("fixture_state")
            spark.sql(f"SELECT * FROM VALUES ('{old_id}',1,12.125BD),('{old_id}',1,12.125BD),('{old_id}',2,CAST(NULL AS DECIMAL(8,3))),('{new_id}',3,99.125BD) AS raw(__industry_snapshot_id,source_key,quantity)").createOrReplaceTempView("fixture_raw")
            query = snapshots.snapshot_view_query("fixture_raw", "fixture_state", ["source_key", "quantity"])
            before = spark.sql(query)
            self.assertEqual(before.count(), 3)
            self.assertEqual({row["source_key"] for row in before.collect()}, {1, 2})
            self.assertEqual(before.where("quantity IS NULL").count(), 1)
            pinned = snapshots.pinned_snapshot_query("fixture_raw", old_id, ["source_key", "quantity"])
            spark.sql(f"SELECT '{new_id}' AS snapshot_id").createOrReplaceTempView("fixture_state")
            after = spark.sql(query)
            self.assertEqual(after.count(), 1)
            self.assertEqual(after.first()["source_key"], 3)
            self.assertEqual(after.columns, ["source_key", "quantity"])
            self.assertEqual(spark.sql(pinned).count(), 3)
            self.assertEqual({row["source_key"] for row in spark.sql(pinned).collect()}, {1, 2})
            spark.sql("SELECT CAST(NULL AS STRING) AS snapshot_id WHERE FALSE").createOrReplaceTempView("fixture_state")
            self.assertEqual(spark.sql(query).count(), 0)
        finally:
            spark.stop()


if __name__ == "__main__":
    unittest.main()