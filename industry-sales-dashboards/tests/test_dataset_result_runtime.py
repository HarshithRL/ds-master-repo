import importlib.util
import json
import sys
import unittest
from datetime import date
from pathlib import Path

from pyspark.sql import SparkSession


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from allocation_stages import freeze_sql_date
from dataset_results import compile_dataset, local_result


class FilteredResultRuntimeTests(unittest.TestCase):
    def test_date_range_boundaries_are_not_frozen_as_an_all_dates_result(self):
        spark = SparkSession.builder.master("local[2]").appName("date-result-filter-equivalence").config("spark.sql.shuffle.partitions", "2").getOrCreate()
        spark.sparkContext.setLogLevel("ERROR")
        source = "SELECT item.order_id, item.changed_date, item.value_eur FROM `synapse-prd`.pbi.dbx_fact_example item WHERE item.industry='34' AND (:cancel_date.min IS NULL OR item.changed_date>=:cancel_date.min) AND (:cancel_date.max IS NULL OR item.changed_date<=:cancel_date.max) ORDER BY item.value_eur DESC"
        try:
            spark.sql("SELECT * FROM VALUES ('O1',DATE '2026-10-01',12.125BD,'34'),('O2',DATE '2026-10-14',20.25BD,'34'),('O2',DATE '2026-10-14',20.25BD,'34'),('O3',CAST(NULL AS DATE),1.25BD,'34'),('O4',DATE '2026-10-10',999.0BD,'99') AS source(order_id,changed_date,value_eur,industry)").createOrReplaceTempView("fixture_items")
            plan = compile_dataset("open_orders", "ds_date_fixture", source, {})
            producer = plan["producers"][0]
            spark.sql(producer["sql"].replace("`synapse-prd`.pbi.dbx_fact_example", "fixture_items")).localCheckpoint(eager=True).createOrReplaceTempView(producer["table"])
            consumer = plan["consumer_sql"].replace(local_result(producer["table"]), "`" + producer["table"] + "`")
            for lower, upper in (("CAST(NULL AS DATE)","CAST(NULL AS DATE)"),("DATE '2026-10-14'","DATE '2026-10-14'"),("DATE '2026-10-02'","DATE '2026-10-13'"),("CAST(NULL AS DATE)","DATE '2026-10-14'")):
                with self.subTest(lower=lower,upper=upper):
                    original = source.replace("`synapse-prd`.pbi.dbx_fact_example", "fixture_items")
                    transformed = consumer
                    for parameter, value in (("cancel_date.min",lower),("cancel_date.max",upper)):
                        original = original.replace(":"+parameter,value)
                        transformed = transformed.replace(":"+parameter,value)
                    expected = spark.sql(original)
                    actual = spark.sql(transformed)
                    self.assertEqual(expected.schema, actual.schema)
                    self.assertEqual(expected.exceptAll(actual).count(), 0)
                    self.assertEqual(actual.exceptAll(expected).count(), 0)
        finally:
            spark.stop()

    def test_native_quote_totals_keep_multisegment_null_duplicate_and_conversion_semantics(self):
        spark = SparkSession.builder.master("local[2]").appName("filtered-result-equivalence").config("spark.sql.shuffle.partitions", "2").getOrCreate()
        spark.sparkContext.setLogLevel("ERROR")
        try:
            source_fact = """
                SELECT * FROM VALUES
                  ('Q1',20260901,10.125D,20261231,'','',1,'YQT','A',''),
                  ('Q1',20260901,20.25D,20261231,'','',1,'YQT','B',''),
                  ('Q1',20260901,20.25D,20261231,'','',1,'YQT','B',''),
                  ('Q2',20260901,5.5D,20260101,'','25',1,'YQT','A',''),
                  ('Q3',20260901,7.75D,20261231,'','24',1,'YQT',CAST(NULL AS STRING),''),
                  ('Q4',20260901,3.25D,20261231,'','',1,'YQT','B',''),
                  ('Q5',20260901,9999.0D,20261231,'','',2,'YQT','A',''),
                  ('Q6',20230101,9999.0D,20261231,'','',1,'YQT','A',''),
                  ('O1',20260902,0.0D,0,'','',1,'YOR','A','Q1')
                AS items(`Sales Document Number`,`Created On`,`Measure Net Value in Euro`,
                  `Quotation Valid To`,`Reason for Rejection`,`Order Reason`,`Sales Organization Key`,
                  `Sales Document Type`,`Application area Description`,`Quote Number`)
            """
            spark.sql(source_fact).createOrReplaceTempView("fixture_items")
            spark.sql("SELECT * FROM VALUES (1,'34','0012'),(2,'99','0099') AS org(`Sales Organization Key`,`Business Unit 2`,`Sales_Organization ID`)").createOrReplaceTempView("fixture_org")
            spark.sql("SELECT * FROM VALUES ('0012','Europe') AS mapping(sales_org_code,cs_team)").createOrReplaceTempView("fixture_mapping")
            document = json.loads((ROOT / "source_dashboards/quotations.metadata.json").read_text())
            dataset = next(item for item in json.loads(document["serialized_dashboard"])["datasets"] if item["name"] == "ds_quotations")
            original = "".join(dataset["queryLines"])
            plan = compile_dataset("quotations", "ds_quotations", original, {})
            def fixture(statement):
                statement = statement.replace("`synapse-prd`.pbi.`dbx_fact_sales_distribution_sales_document_item`", "fixture_items")
                statement = statement.replace("`synapse-prd`.pbi.`dbx_dim_sales_organization`", "fixture_org")
                statement = statement.replace("`supply_chain_sandbox_d`.`datamodel`.`cs_team_sales_org_mapping`", "fixture_mapping")
                statement = statement.replace("`${var.catalog}`.gold.`${var.mapping_table_name}`", "fixture_mapping")
                return freeze_sql_date(statement, date(2026, 10, 14))
            consumer = fixture(plan["consumer_sql"])
            for producer in plan["producers"]:
                result = spark.sql(fixture(producer["sql"])).localCheckpoint(eager=True)
                result.createOrReplaceTempView(producer["component"])
                if producer["table"]:
                    result.createOrReplaceTempView(producer["table"])
                    consumer = consumer.replace(local_result(producer["table"]), "`" + producer["table"] + "`")
            for selected in ("CAST(NULL AS ARRAY<STRING>)", "ARRAY()", "ARRAY('A')", "ARRAY('B')", "ARRAY('A','B')", "ARRAY('missing')"):
                with self.subTest(filter=selected):
                    expected = spark.sql(fixture(original).replace(":segment_filter", selected))
                    actual = spark.sql(consumer.replace(":segment_filter", selected))
                    self.assertEqual(expected.schema, actual.schema)
                    self.assertEqual(expected.exceptAll(actual).count(), 0)
                    self.assertEqual(actual.exceptAll(expected).count(), 0)
            all_rows = spark.sql(consumer.replace(":segment_filter", "ARRAY()")).collect()
            self.assertEqual(sum(row["total_quotes"] for row in all_rows), 4)
            self.assertEqual(sum(row["converted_quotes"] for row in all_rows), 2)
        finally:
            spark.stop()

    def test_country_and_segment_filter_remain_before_quote_grouping(self):
        source = """
            WITH quotes AS (
              SELECT i.quote_id, ROUND(SUM(i.value_eur),0) AS quote_value, MAX(c.country) AS country
              FROM `synapse-prd`.pbi.dbx_fact_items i JOIN `synapse-prd`.pbi.dbx_dim_customers c ON i.customer_key=c.customer_key
              WHERE i.industry='34' AND (:segment_filter IS NULL OR CARDINALITY(:segment_filter)=0 OR array_contains(:segment_filter,i.segment))
                AND (:country_filter IS NULL OR CARDINALITY(:country_filter)=0 OR array_contains(:country_filter,c.country))
              GROUP BY i.quote_id
            ) SELECT * FROM quotes WHERE (:priority_filter IS NULL OR CARDINALITY(:priority_filter)=0 OR array_contains(:priority_filter,country))
        """
        spark = SparkSession.builder.master("local[2]").appName("quote-group-filter-equivalence").config("spark.sql.shuffle.partitions", "2").getOrCreate()
        spark.sparkContext.setLogLevel("ERROR")
        try:
            spark.sql("SELECT * FROM VALUES ('Q1',10.125D,1,'A','34'),('Q1',20.25D,2,'B','34'),('Q1',20.25D,2,'B','34'),('Q2',7.25D,1,CAST(NULL AS STRING),'34'),('Q3',9999.0D,1,'A','99') AS items(quote_id,value_eur,customer_key,segment,industry)").createOrReplaceTempView("fixture_items")
            spark.sql("SELECT * FROM VALUES (1,'BE'),(2,'DE') AS customers(customer_key,country)").createOrReplaceTempView("fixture_customers")
            plan = compile_dataset("quotations", "ds_fixture", source, {})
            def fixture(statement):
                return statement.replace("`synapse-prd`.pbi.dbx_fact_items", "fixture_items").replace("`synapse-prd`.pbi.dbx_dim_customers", "fixture_customers")
            consumer = fixture(plan["consumer_sql"])
            for producer in plan["producers"]:
                result = spark.sql(fixture(producer["sql"])).localCheckpoint(eager=True)
                result.createOrReplaceTempView(producer["component"])
                if producer["table"]:
                    result.createOrReplaceTempView(producer["table"])
                    consumer = consumer.replace(local_result(producer["table"]), "`" + producer["table"] + "`")
            for segment, country, priority in (("ARRAY()","ARRAY()","ARRAY()"),("ARRAY('A','B')","ARRAY('BE')","ARRAY()"),("ARRAY('B')","ARRAY('DE')","ARRAY('DE')"),("ARRAY()","ARRAY('DE')","ARRAY('BE')")):
                with self.subTest(segment=segment,country=country,priority=priority):
                    original = fixture(source)
                    rewritten = consumer
                    for parameter, value in (("segment_filter",segment),("country_filter",country),("priority_filter",priority)):
                        original = original.replace(":"+parameter,value)
                        rewritten = rewritten.replace(":"+parameter,value)
                    expected = spark.sql(original)
                    actual = spark.sql(rewritten)
                    self.assertEqual(expected.exceptAll(actual).count(), 0)
                    self.assertEqual(actual.exceptAll(expected).count(), 0)
        finally:
            spark.stop()


if __name__ == "__main__":
    unittest.main()