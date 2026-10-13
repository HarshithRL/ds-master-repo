import importlib.util
import unittest
from datetime import date
from pathlib import Path

from pyspark import StorageLevel
from pyspark.sql import SparkSession


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("allocation_stages", ROOT / "src/allocation_stages.py")
staging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(staging)


class AllocationStageRuntimeTests(unittest.TestCase):
    def test_freezing_preserves_current_month_ytd_future_and_due_boundaries(self):
        spark = SparkSession.builder.master("local[2]").appName("allocation-date-equivalence").config("spark.sql.shuffle.partitions", "2").getOrCreate()
        spark.sparkContext.setLogLevel("ERROR")
        source = """
            WITH boundary_dates AS (
                SELECT EXPLODE(ARRAY(
                    CAST(DATE_TRUNC('YEAR', CURRENT_DATE()) AS DATE),
                    DATE_ADD(CAST(DATE_TRUNC('MONTH', CURRENT_DATE()) AS DATE), -1),
                    CAST(DATE_TRUNC('MONTH', CURRENT_DATE()) AS DATE),
                    DATE_ADD(CURRENT_DATE(), -1), CURRENT_DATE(),
                    DATE_ADD(CURRENT_DATE(), 1), LAST_DAY(CURRENT_DATE()),
                    DATE_ADD(LAST_DAY(CURRENT_DATE()), 1)
                )) AS gi_date
            ), buckets AS (
                SELECT gi_date,
                    CASE WHEN gi_date BETWEEN DATE_TRUNC('MONTH', CURRENT_DATE()) AND LAST_DAY(CURRENT_DATE()) THEN 'CM'
                         WHEN gi_date >= DATE_TRUNC('YEAR', CURRENT_DATE()) AND gi_date < DATE_TRUNC('MONTH', CURRENT_DATE()) THEN 'YTD'
                         WHEN gi_date > LAST_DAY(CURRENT_DATE()) THEN 'FUT' ELSE 'PRE' END AS scope,
                    gi_date < CURRENT_DATE() AS is_past_due,
                    ADD_MONTHS(CURRENT_DATE(), -12) AS lookback,
                    CAST(DATE_FORMAT(DATE_TRUNC('YEAR', CURRENT_DATE()), 'yyyyMMdd') AS INT) AS year_key,
                    'CURRENT_DATE()' AS literal_text
                FROM boundary_dates
            ) SELECT * FROM buckets
        """
        cached = []
        try:
            business_date = spark.sql("SELECT CURRENT_DATE() AS business_date").first()["business_date"]
            expected = spark.sql(source).cache()
            expected.count()
            stages, final = staging.build_stages(source, business_date)
            for name, statement in stages:
                frame = spark.sql(statement).localCheckpoint(eager=True)
                cached.append((name, frame))
                frame.count()
                frame.createOrReplaceTempView(name)
            actual = spark.sql(final)
            self.assertEqual(expected.exceptAll(actual).count(), 0)
            self.assertEqual(actual.exceptAll(expected).count(), 0)
            self.assertEqual(actual.count(), 8)
            self.assertEqual({row["literal_text"] for row in actual.collect()}, {"CURRENT_DATE()"})
        finally:
            for name, frame in reversed(cached):
                spark.catalog.dropTempView(name)
                frame.unpersist()
            spark.stop()

    def test_staging_preserves_duplicate_null_fractional_union_and_window_results(self):
        spark = SparkSession.builder.master("local[2]").appName("allocation-stage-equivalence").config("spark.sql.shuffle.partitions", "2").getOrCreate()
        spark.sparkContext.setLogLevel("ERROR")
        cached = []
        source = """
            WITH source_rows AS (
                SELECT * FROM VALUES
                  ('order_1', 1, 221.904BD, 1000.125BD),
                  ('order_1', 2, 19.375BD, 83.117BD),
                  ('order_1', 2, 19.375BD, 83.117BD),
                  ('order_2', 1, 0.0BD, 5.25BD),
                  ('order_3', 1, 3.75BD, CAST(NULL AS DECIMAL(18, 3)))
                AS source(order_number, item_number, quantity, value_eur)
            ), runtime_mapping AS (
                SELECT * FROM VALUES ('order_1', 'Europe'), ('order_2', 'Asia')
                AS mapping(order_number, team)
            ), scoped_orders AS (
                SELECT source.*, mapping.team FROM source_rows source
                LEFT JOIN runtime_mapping mapping ON source.order_number = mapping.order_number
            ), totals AS (
                SELECT order_number, SUM(quantity) AS total FROM scoped_orders GROUP BY order_number
            ), portions AS (
                SELECT source.*, source.value_eur * (source.quantity / NULLIF(totals.total, 0)) AS allocated
                FROM scoped_orders source JOIN totals ON source.order_number = totals.order_number
            ), schedule_window AS (
                SELECT *, SUM(quantity) OVER (PARTITION BY order_number ORDER BY item_number
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative FROM portions
            ), allocation_union AS (
                SELECT order_number, team, allocated, cumulative FROM schedule_window
                UNION ALL SELECT order_number, team, allocated, cumulative FROM portions
                JOIN schedule_window USING (order_number, item_number, team, quantity, value_eur, allocated)
            ) SELECT order_number, team, SUM(allocated) AS allocated, MAX(cumulative) AS cumulative
              FROM allocation_union GROUP BY order_number, team
        """
        try:
            expected = spark.sql(source).cache()
            expected.count()
            stages, final = staging.build_stages(source, date(2026, 10, 13))
            for name, statement in stages:
                frame = spark.sql(statement).localCheckpoint(eager=True)
                cached.append((name, frame))
                frame.count()
                frame.createOrReplaceTempView(name)
            actual = spark.sql(final)
            self.assertEqual(expected.exceptAll(actual).count(), 0)
            self.assertEqual(actual.exceptAll(expected).count(), 0)
            self.assertEqual(actual.count(), 3)
        finally:
            for name, frame in reversed(cached):
                spark.catalog.dropTempView(name)
                frame.unpersist()
            spark.stop()


if __name__ == "__main__":
    unittest.main()