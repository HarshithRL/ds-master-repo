import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

from pyspark import StorageLevel
from pyspark.sql import SparkSession, functions as sql_functions


parser = argparse.ArgumentParser()
parser.add_argument("--catalog", required=True)
parser.add_argument("--source-catalog", required=True)
parser.add_argument("--target", required=True)
parser.add_argument("--config-path", required=True)
args = parser.parse_args()
config_path = Path(args.config_path)
sys.path.insert(0, str(config_path.parent))

from industry_config import validate_environment
from source_snapshots import SNAPSHOT_PREFIX, quote_column, snapshot_view_query, validate_complete_receipts, validate_manifest


spark = SparkSession.builder.getOrCreate()
catalog = args.catalog
validate_environment(catalog, args.source_catalog, args.target, spark.conf.get("spark.databricks.clusterUsageTags.orgId"))
suffix = "_dev" if args.target == "D" else ""
sources = validate_manifest(json.loads((config_path / "source_snapshots.json").read_text())["sources"])
snapshot_id = uuid4().hex
state = f"{catalog}.gold.industry_sales_source_snapshot_state{suffix}"
owner = "industry-sales-dashboards"
reserved = "__industry_snapshot_id"


def check_owned(destination):
    if spark.catalog.tableExists(destination):
        properties = {row["key"]: row["value"] for row in spark.sql(f"SHOW TBLPROPERTIES {destination}").collect()}
        if properties.get("industry_sales.bundle") != owner:
            raise ValueError(f"Refusing to change a relation not owned by this bundle: {destination}")


for layer in ("bronze", "silver", "gold"):
    spark.sql(f"DESCRIBE SCHEMA {catalog}.{layer}").collect()
check_owned(state)
for source in sources:
    check_owned(f"{catalog}.bronze.`{source['snapshot_table'].replace(SNAPSHOT_PREFIX, 'industry_sales_raw_', 1)}{suffix}`")
    check_owned(f"{catalog}.silver.`{source['snapshot_table']}{suffix}`")

spark.sql(
    f"CREATE TABLE IF NOT EXISTS {state} USING DELTA "
    "TBLPROPERTIES ('industry_sales.bundle'='industry-sales-dashboards') AS "
    "SELECT CAST(NULL AS STRING) AS snapshot_id, CAST(NULL AS DATE) AS snapshot_as_of_date, "
    "CAST(NULL AS TIMESTAMP) AS snapshot_completed_at, CAST(NULL AS STRING) AS source_receipts WHERE FALSE"
).collect()
previous = spark.table(state).collect()
if len(previous) > 1:
    raise ValueError("Snapshot state contains multiple active batches")
previous_id = previous[0]["snapshot_id"] if previous else None
business_date = spark.sql("SELECT CURRENT_DATE() AS business_date").first()["business_date"]
receipts = []
for source in sources:
    projection = "*" if source["columns"] is None else ", ".join(quote_column(column) for column in source["columns"])
    raw = f"{catalog}.bronze.`{source['snapshot_table'].replace(SNAPSHOT_PREFIX, 'industry_sales_raw_', 1)}{suffix}`"
    view = f"{catalog}.silver.`{source['snapshot_table']}{suffix}`"
    frame = spark.sql(f"SELECT {projection} FROM `{args.source_catalog}`.pbi.`{source['source_table']}`").persist(StorageLevel.DISK_ONLY)
    try:
        if reserved in frame.columns or any("`" in column for column in frame.columns):
            raise ValueError("Source has a reserved or invalid snapshot column")
        count = frame.count()
        if spark.catalog.tableExists(raw):
            actual_types = [(field.name, field.dataType) for field in spark.table(raw).schema.fields if field.name != reserved]
            if actual_types != [(field.name, field.dataType) for field in frame.schema.fields]:
                raise ValueError(f"Source schema changed; explicit migration required: {raw}")
        captured = frame.withColumn(reserved, sql_functions.lit(snapshot_id))
        if not spark.catalog.tableExists(raw):
            captured.limit(0).createOrReplaceTempView("industry_raw_source_schema")
            spark.sql(
                f"CREATE TABLE {raw} USING DELTA "
                "TBLPROPERTIES ('industry_sales.bundle'='industry-sales-dashboards', 'delta.columnMapping.mode'='name') "
                "AS SELECT * FROM industry_raw_source_schema"
            ).collect()
        captured.write.format("delta").mode("append").saveAsTable(raw)
        actual = spark.table(raw).where(sql_functions.col(reserved) == snapshot_id).select(*[sql_functions.col(quote_column(column)) for column in frame.columns])
        if frame.exceptAll(actual).limit(1).count() or actual.exceptAll(frame).limit(1).count():
            raise ValueError(f"Source snapshot write/read parity failed: {raw}")
        spark.sql(
            f"CREATE OR REPLACE VIEW {view} TBLPROPERTIES ('industry_sales.bundle'='industry-sales-dashboards') AS "
            + snapshot_view_query(raw, state, frame.columns)
        ).collect()
        receipts.append({"source": source["source_table"], "rows": count, "columns": frame.columns})
        print(json.dumps(receipts[-1]), flush=True)
    finally:
        frame.unpersist()

validate_complete_receipts(sources, receipts)
completed = spark.createDataFrame([(snapshot_id, business_date, json.dumps(receipts))], "snapshot_id STRING, snapshot_as_of_date DATE, source_receipts STRING").withColumn("snapshot_completed_at", sql_functions.current_timestamp())
completed.createOrReplaceTempView("industry_completed_source_snapshot")
spark.sql(
    f"CREATE OR REPLACE TABLE {state} USING DELTA TBLPROPERTIES ('industry_sales.bundle'='industry-sales-dashboards') "
    "AS SELECT snapshot_id, snapshot_as_of_date, snapshot_completed_at, source_receipts FROM industry_completed_source_snapshot"
).collect()
print(json.dumps({"snapshot_id": snapshot_id, "business_date": business_date.isoformat(), "sources": len(receipts), "published": True}), flush=True)
keep = [snapshot_id] + ([previous_id] if previous_id else [])
for source in sources:
    raw = f"{catalog}.bronze.`{source['snapshot_table'].replace(SNAPSHOT_PREFIX, 'industry_sales_raw_', 1)}{suffix}`"
    retained = ", ".join(f"'{batch}'" for batch in keep)
    spark.sql(f"DELETE FROM {raw} WHERE `{reserved}` NOT IN ({retained})").collect()