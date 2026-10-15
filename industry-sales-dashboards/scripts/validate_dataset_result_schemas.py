import json
import sys
from pathlib import Path

from databricks.sdk import WorkspaceClient
from pyspark.errors import AnalysisException, ParseException
from pyspark.sql import SparkSession
from pyspark.sql.types import StructField, StructType


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from allocation_stages import query_parts
from dataset_results import local_result, parameter_defaults, table_edits


def main():
    workspace = WorkspaceClient(profile="DEFAULT")
    if workspace.config.host.rstrip("/") != "https://adb-7181820732839861.1.azuredatabricks.net":
        raise ValueError("Result schema analysis is DEV-only")
    spark = SparkSession.builder.master("local[2]").appName("result-schema-analysis").config("spark.sql.shuffle.partitions", "2").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    sources = json.loads((ROOT / "src/config/source_dependencies.json").read_text())["pbi_tables"]
    plans = json.loads((ROOT / "src/config/dashboard_results.json").read_text())["datasets"]
    replacements = {"supply_chain_sandbox_d.datamodel.cs_team_sales_org_mapping": "fixture_mapping", "${var.catalog}.gold.${var.mapping_table_name}": "fixture_mapping"}
    receipts = []
    try:
        for name in sources:
            table = workspace.tables.get("synapse-prd.pbi." + name)
            fields = [StructField.fromJson(json.loads(column.type_json)) for column in table.columns]
            fixture_name = "fixture_" + name.replace("-", "_")
            spark.createDataFrame([], StructType(fields)).createOrReplaceTempView(fixture_name)
            replacements["synapse-prd.pbi." + name] = fixture_name
            replacements["${var.source_catalog}.pbi." + name] = fixture_name
        spark.sql("SELECT CAST(NULL AS STRING) AS sales_org_code, CAST(NULL AS STRING) AS sales_organization, CAST(NULL AS STRING) AS cs_team WHERE FALSE").createOrReplaceTempView("fixture_mapping")
        for plan in plans:
            metadata = json.loads((ROOT / "source_dashboards" / f"{plan['dashboard']}.metadata.json").read_text())
            original = next(item for item in json.loads(metadata["serialized_dashboard"])["datasets"] if item["name"] == plan["dataset"])
            baseline = table_edits(parameter_defaults("".join(original["queryLines"])), replacements)
            try:
                expected = spark.sql(baseline).schema
            except (AnalysisException, ParseException) as error:
                if error.getErrorClass() == "DATATYPE_MISMATCH.STACK_COLUMN_DIFF_TYPES" or (isinstance(error, ParseException) and "QUALIFY" in str(error)):
                    receipts.append({"dashboard": plan["dashboard"], "dataset": plan["dataset"], "native_runtime_required": error.getErrorClass()})
                    print(f"UNVERIFIED native engine contract: {plan['dataset']}: {error.getErrorClass()}", flush=True)
                    continue
                raise
            temporary = []
            consumer = plan["consumer_sql"]
            try:
                for producer in plan["producers"]:
                    statement = table_edits(producer["sql"], replacements)
                    ctes, final = query_parts(statement)
                    for name, cte in ctes:
                        spark.sql(cte).createOrReplaceTempView(name)
                        temporary.append(name)
                    result = spark.sql(final)
                    result.createOrReplaceTempView(producer["component"])
                    temporary.append(producer["component"])
                    if producer["table"]:
                        spark.createDataFrame([], result.schema).createOrReplaceTempView(producer["table"])
                        temporary.append(producer["table"])
                        consumer = consumer.replace(local_result(producer["table"]), "`" + producer["table"] + "`")
                actual = spark.sql(table_edits(parameter_defaults(consumer), replacements)).schema
                required = [(field.name, field.dataType) for field in expected.fields]
                observed = [(field.name, field.dataType) for field in actual.fields]
                if required != observed:
                    raise ValueError(f"Changed dataset output contract: {plan['dataset']}: {required} != {observed}")
                receipts.append({"dashboard": plan["dashboard"], "dataset": plan["dataset"], "schema": actual.jsonValue(), "verified": True})
                print(f"PASS producer/consumer native output schema: {plan['dashboard']}:{plan['dataset']}", flush=True)
            finally:
                for name in set(temporary):
                    spark.catalog.dropTempView(name)
        (ROOT / "validation/dataset_result_schemas.json").write_text(json.dumps(receipts, indent=2) + "\n")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()