import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pyspark.sql import SparkSession


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dataset_results import local_result, table_edits
import warehouse_results as warehouse


class CancellationWarehouseRuntimeTests(unittest.TestCase):
    def test_native_cancellation_query_retains_exact_values_and_all_date_selections(self):
        spark = SparkSession.builder.master("local[2]").appName("cancellation-warehouse-parity").config("spark.sql.shuffle.partitions", "2").getOrCreate()
        spark.sparkContext.setLogLevel("ERROR")
        try:
            spark.sql("SELECT * FROM VALUES ('O1','10',CAST(12.125 AS DECIMAL(38,14)),'C','01',20261001,20261015,'YOR',10,20,1),('O1','10',CAST(12.125 AS DECIMAL(38,14)),'C','01',20261001,20261015,'YOR',10,20,1),('O2','20',CAST(7.75 AS DECIMAL(38,14)),'C','02',20261001,20261010,'YOR',999,999,1),('O3','30',CAST(9999 AS DECIMAL(38,14)),'C','03',20261001,20261015,'YOR',10,20,2),('O4','40',CAST(999 AS DECIMAL(38,14)),'A','01',20261001,20261015,'YOR',10,20,1),('O5','50',CAST(NULL AS DECIMAL(38,14)),'C',CAST(NULL AS STRING),20261001,CAST(NULL AS INT),'YSO',CAST(NULL AS INT),CAST(NULL AS INT),1) AS source(`Order Number`,`Order Item Number`,`Net Value Euro`,`Rejection Status`,`Rejection Reason`,`Date - Item Creation`,`Date - Item Changed`,`Document Type`,`FK Sold to Party`,`FK Material`,`FK Sales Organization`)").createOrReplaceTempView("fixture_orders")
            spark.sql("SELECT * FROM VALUES (1,'0012','BE','34'),(2,'0099','DE','99') AS org(`Sales Organization Key`,`Sales_Organization ID`,`Country key`,`Business Unit 2`)").createOrReplaceTempView("fixture_org")
            spark.sql("SELECT * FROM VALUES ('0012','Europe') AS mapping(sales_org_code,cs_team)").createOrReplaceTempView("fixture_mapping")
            spark.sql("SELECT * FROM VALUES (10,'Customer') AS customer(`Customer Key`,`Name 1`)").createOrReplaceTempView("fixture_customer")
            spark.sql("SELECT * FROM VALUES (20,'M1','Material') AS material(`Material Key`,`Material Code`,`Material Text`)").createOrReplaceTempView("fixture_material")
            spark.sql("SELECT * FROM VALUES ('M1','Group'),('M1','Group') AS hierarchy(`Material Code`,`L2 Product Description`)").createOrReplaceTempView("fixture_hierarchy")
            spark.sql("SELECT * FROM VALUES ('O1','10','A'),('O1','10','B') AS item(`Sales Document Number`,`Sales Document Item Number`,`Application area Description`)").createOrReplaceTempView("fixture_item")
            replacements = {"dbx_fact_o2c_-_self_service_-_sales_orders": "fixture_orders", "dbx_dim_sales_organization": "fixture_org", "dbx_dim_customer": "fixture_customer", "dbx_dim_material": "fixture_material", "dbx_dim_product_hierarchy": "fixture_hierarchy", "dbx_fact_sales_distribution_sales_document_item": "fixture_item"}
            identities = {catalog + ".pbi." + table: fixture for table, fixture in replacements.items() for catalog in ("synapse-prd", "${var.source_catalog}")}
            identities.update({"supply_chain_sandbox_d.datamodel.cs_team_sales_org_mapping": "fixture_mapping", "${var.catalog}.gold.${var.mapping_table_name}": "fixture_mapping"})
            plan = next(item for item in json.loads((ROOT / "src/config/dashboard_results.json").read_text())["datasets"] if item["dataset"] == warehouse.CANCELLATION_DATASET)
            producer = plan["producers"][0]
            source = table_edits(producer["sql"], identities)
            client = Mock()

            def execute_statement(**request):
                spark.sql(request["statement"]).collect()
                return SimpleNamespace(statement_id="fixture-write", status=SimpleNamespace(state=SimpleNamespace(value="SUCCEEDED")), manifest=None)

            client.statement_execution.execute_statement.side_effect = execute_statement
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "stage"
                with patch.object(warehouse, "warehouse_stage_sql", side_effect=lambda statement, destination: f"INSERT OVERWRITE DIRECTORY '{destination}' USING PARQUET\n" + statement):
                    result = warehouse.stage_cancellation_warehouse(spark, client, "69ada62b2fb9b9e2", source, path)
                    self.assertEqual(result.count(), 10)
                    self.assertEqual(result.exceptAll(spark.sql(source)).count(), 0)
                    self.assertEqual(spark.sql(source).exceptAll(result).count(), 0)
                    result.createOrReplaceTempView("fixture_cancellation_result")
                    for lower, upper in (("CAST(NULL AS DATE)", "CAST(NULL AS DATE)"), ("DATE '2026-10-15'", "DATE '2026-10-15'"), ("DATE '2026-10-10'", "DATE '2026-10-10'"), ("DATE '2026-10-11'", "DATE '2026-10-14'"), ("CAST(NULL AS DATE)", "DATE '2026-10-15'")):
                        with self.subTest(lower=lower, upper=upper):
                            original = table_edits(plan["source_sql"], identities)
                            consumer = plan["consumer_sql"].replace(local_result(producer["table"]), "fixture_cancellation_result")
                            for parameter, value in ((":cancel_date.min", lower), (":cancel_date.max", upper)):
                                original = original.replace(parameter, value)
                                consumer = consumer.replace(parameter, value)
                            expected = spark.sql(original)
                            actual = spark.sql(consumer)
                            self.assertEqual([(field.name, field.dataType) for field in expected.schema.fields], [(field.name, field.dataType) for field in actual.schema.fields])
                            self.assertEqual(expected.exceptAll(actual).count(), 0)
                            self.assertEqual(actual.exceptAll(expected).count(), 0)
                    before = client.statement_execution.execute_statement.call_count
                    with self.assertRaises(FileExistsError):
                        warehouse.stage_cancellation_warehouse(spark, client, "69ada62b2fb9b9e2", source, path)
                    self.assertEqual(client.statement_execution.execute_statement.call_count, before)
                    empty = warehouse.stage_cancellation_warehouse(spark, client, "69ada62b2fb9b9e2", "SELECT * FROM (" + source + ") native_rows WHERE FALSE", Path(directory) / "empty")
                    self.assertEqual(empty.count(), 0)
        finally:
            spark.stop()


if __name__ == "__main__":
    unittest.main()