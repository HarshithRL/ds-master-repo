import importlib.util
import json
import unittest
from datetime import date
from pathlib import Path

from pyspark import StorageLevel
from pyspark.sql import SparkSession


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("native_allocation_stages", ROOT / "src/allocation_stages.py")
staging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(staging)


class NativeAllocationRuntimeTests(unittest.TestCase):
    def test_full_native_query_matches_staged_fractional_business_cases(self):
        spark = SparkSession.builder.master("local[2]").appName("native-allocation-equivalence").config("spark.sql.shuffle.partitions", "2").getOrCreate()
        spark.sparkContext.setLogLevel("ERROR")
        fixtures = {
            "dbx_fact_sales_distribution_sales_document_item": """
                SELECT * FROM VALUES
                ('fully_confirmed','10',1000.125D,10.5D,1,42,'Market','Open',1,CAST(NULL AS STRING),'Standard Order','YOR',20260115),
                ('partially_confirmed','10',83.117D,8.5D,1,42,'Market','Open',1,CAST(NULL AS STRING),'Standard Order','YOR',20260115),
                ('unconfirmed','10',221.904D,3.75D,1,42,'Market','Open',1,CAST(NULL AS STRING),'Standard Order','YOR',20260115),
                ('fallback_date','10',50.25D,0.0D,1,777,'Market','Open',1,CAST(NULL AS STRING),'Standard Order','YOR',20260115),
                ('future_order','10',73.0D,11.125D,1,42,'Market','Open',1,CAST(NULL AS STRING),'Standard Order','YOR',20260115),
                ('rejected','10',9999.0D,1.0D,1,42,'Market','Open',1,'C','Standard Order','YOR',20260115),
                ('outside_industry','10',9999.0D,1.0D,1,42,'Market','Open',2,CAST(NULL AS STRING),'Standard Order','YOR',20260115)
                AS items(`Sales Document Number`,`Sales Document Item Number`,`Measure Net Value in Euro`,
                         `Measure Sales Order Quantity`,`Delivery Date To Key`,`Plant Key`,
                         `Application area Description`,`Order Status`,`Sales Organization Key`,
                         `Rejection Status`,`Sales Document Type Description`,`Sales Document Type`,`Created On`)
            """,
            "dbx_dim_sales_organization": """
                SELECT * FROM VALUES (1,'34','0012'),(2,'99','0099')
                AS organizations(`Sales Organization Key`,`Business Unit 2`,`Sales_Organization ID`)
            """,
            "cs_team_sales_org_mapping": """
                SELECT * FROM VALUES ('0012','Europe') AS mapping(sales_org_code,cs_team)
            """,
            "dbx_fact_sales_distribution_schedule_line": """
                SELECT * FROM VALUES
                ('fully_confirmed','10',20261001,5.25D,5.25D),
                ('fully_confirmed','10',20261020,5.25D,5.25D),
                ('fully_confirmed','10',20261001,5.25D,0.0D),
                ('partially_confirmed','10',20261002,3.75D,3.75D),
                ('partially_confirmed','10',20261018,0.0D,4.75D),
                ('unconfirmed','10',20260925,0.0D,3.75D),
                ('future_order','10',20261105,11.125D,11.125D),
                ('rejected','10',20261010,1.0D,1.0D),
                ('outside_industry','10',20261010,1.0D,1.0D)
                AS schedules(`Sales Document Number`,`Sales Document Item Number`,`Goods Issue Date`,
                             `Measure Confirmed Quantity`,`Measure Order Quantity`)
            """,
            "dbx_fact_billing_document_line_item": """
                SELECT * FROM VALUES
                ('fully_confirmed','10',3.5D,'M'),('fully_confirmed','10',-1.0D,'M'),
                ('fully_confirmed','10',99.0D,'N'),('partially_confirmed','10',2.125D,'M'),
                ('fallback_date','10',1.0D,'M')
                AS billings(`Sales Document Number`,`Sales Document Item Number`,`Billed Quantity`,`SD Document Category`)
            """,
            "dbx_fact_sales_distribution_delivery_item": """
                SELECT * FROM VALUES
                ('fully_confirmed','10',6.125D,'C'),('fully_confirmed','10',99.0D,'A'),
                ('partially_confirmed','10',3.75D,'C')
                AS deliveries(`Reference Document`,`Reference Item`,`Measure Actual Delivery Quantity`,`Goods Movement Status`)
            """,
            "dbx_date_delivery": """
                SELECT * FROM VALUES (1,DATE '2026-10-12') AS dates(`Date Delivery Key`,`Date Delivery`)
            """,
            "dbx_dim_plant": """
                SELECT * FROM VALUES (42,'Plant 42') AS plants(`Plant Key`,`Plant Code & Text`)
            """,
        }
        cached = []
        expected = None
        try:
            metadata = json.loads((ROOT / "source_dashboards/open_orders.metadata.json").read_text())
            dataset = next(item for item in json.loads(metadata["serialized_dashboard"])["datasets"] if item["name"] == "ds_overview_allocation")
            source = "".join(dataset["queryLines"])
            for name, statement in fixtures.items():
                spark.sql(statement).createOrReplaceTempView("fixture_" + name)
                if name == "cs_team_sales_org_mapping":
                    source = source.replace("`supply_chain_sandbox_d`.`datamodel`.`cs_team_sales_org_mapping`", "fixture_" + name)
                else:
                    source = source.replace(f"`synapse-prd`.pbi.`{name}`", "fixture_" + name)
            source = staging.freeze_sql_date(source, date(2026, 10, 13))
            expected = spark.sql(source).persist(StorageLevel.DISK_ONLY)
            expected_count = expected.count()
            stages, final = staging.build_stages(source, date(2026, 10, 13))
            for name, statement in stages:
                frame = spark.sql(statement).localCheckpoint(eager=True)
                cached.append((name, frame))
                frame.count()
                frame.createOrReplaceTempView(name)
            actual = spark.sql(final)
            self.assertGreater(expected_count, 0)
            self.assertEqual(tuple(actual.columns), ("scope", "cs_team", "segment", "plant", "bucket", "value_eur"))
            self.assertEqual(expected.exceptAll(actual).count(), 0)
            self.assertEqual(actual.exceptAll(expected).count(), 0)
            self.assertEqual({row["scope"] for row in actual.select("scope").distinct().collect()}, {"CM", "YTD", "FUT"})
        finally:
            if expected is not None:
                expected.unpersist()
            for name, frame in reversed(cached):
                spark.catalog.dropTempView(name)
                frame.unpersist()
            spark.stop()


if __name__ == "__main__":
    unittest.main()