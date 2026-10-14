import json
import sys
from pathlib import Path

from databricks.sdk import WorkspaceClient
from pyspark.sql import SparkSession
from pyspark.errors import AnalysisException, ParseException
from pyspark.sql.types import StructField, StructType


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from source_snapshots import replace_source_references
from preflight_sql import prepare_query


def main():
    workspace = WorkspaceClient(profile="DEFAULT")
    if workspace.config.host.rstrip("/") != "https://adb-7181820732839861.1.azuredatabricks.net":
        raise ValueError("Source schema verification is DEV-only")
    spark = SparkSession.builder.master("local[2]").appName("snapshot-schema-analysis").config("spark.sql.shuffle.partitions", "2").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    sources = json.loads((ROOT / "src/config/source_snapshots.json").read_text())["sources"]
    mapping = json.loads((ROOT / "src/config/cs_team_sales_org_mapping.json").read_text())["rows"]
    receipts = []
    try:
        for source in sources:
            table = workspace.tables.get("synapse-prd.pbi." + source["source_table"])
            fields = {column.name: StructField.fromJson(json.loads(column.type_json)) for column in table.columns}
            projection = source["columns"] or [column.name for column in table.columns]
            if set(projection) - set(fields):
                raise ValueError(f"Missing source columns: {source['source_table']}")
            spark.createDataFrame([], StructType([fields[column] for column in projection])).createOrReplaceTempView(source["snapshot_table"])
            spark.createDataFrame([], StructType(list(fields.values()))).createOrReplaceTempView("full_" + source["snapshot_table"])
        for key in ("open_orders", "quotations"):
            metadata = json.loads((ROOT / "source_dashboards" / f"{key}.metadata.json").read_text())
            for dataset in json.loads(metadata["serialized_dashboard"])["datasets"]:
                query = prepare_query("".join(dataset["queryLines"]), "synapse-prd", mapping)
                query = replace_source_references(query, "fixture", "")
                for source in sources:
                    query = query.replace(f"`fixture`.silver.`{source['snapshot_table']}`", f"`{source['snapshot_table']}`")
                baseline = query
                for source in sources:
                    baseline = baseline.replace(f"`{source['snapshot_table']}`", f"`full_{source['snapshot_table']}`")
                try:
                    schema = spark.sql(query).schema
                except (AnalysisException, ParseException) as error:
                    unsupported = error.getErrorClass() == "DATATYPE_MISMATCH.STACK_COLUMN_DIFF_TYPES" or (isinstance(error, ParseException) and "QUALIFY" in str(error))
                    if not unsupported:
                        raise
                    try:
                        spark.sql(baseline).schema
                    except (AnalysisException, ParseException) as baseline_error:
                        if baseline_error.getErrorClass() != error.getErrorClass():
                            raise
                    else:
                        raise ValueError("Projected query fails but full source schema succeeds") from error
                    receipts.append({"dashboard": key, "dataset": dataset["name"], "local_analyzer_limit": error.getErrorClass(), "same_failure_with_full_source_schema": True})
                    print(f"UNVERIFIED native engine feature: {key}:{dataset['name']}: {error.getErrorClass()} (identical full-source failure)", flush=True)
                    continue
                baseline_schema = spark.sql(baseline).schema
                if schema != baseline_schema:
                    raise ValueError(f"Projected query changes output types: {key}:{dataset['name']}")
                receipts.append({"dashboard": key, "dataset": dataset["name"], "columns": schema.jsonValue()})
                print(f"PASS projected/full schema equivalence: {key}:{dataset['name']}", flush=True)
        destination = ROOT / "validation/dev_projected_query_schemas.json"
        destination.write_text(json.dumps(receipts, indent=2) + "\n")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()