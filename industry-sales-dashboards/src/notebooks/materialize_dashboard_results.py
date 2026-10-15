import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from uuid import uuid4

from pyspark.sql import SparkSession, functions as sql_functions


parser = argparse.ArgumentParser()
for parameter in ("catalog", "source-catalog", "target", "mapping-table-name", "config-path"):
    parser.add_argument("--" + parameter, required=True)
args = parser.parse_args()
config_path = Path(args.config_path)
sys.path.insert(0, str(config_path.parent))

from allocation_stages import freeze_sql_date, query_parts
from industry_config import RESULT_STATE_TABLE_NAME, validate_environment, validate_table_name
from dataset_results import result_storage_name, unique_result_producers, validate_result_receipts
from durable_results import cleanup_result_scratch, result_dataset_scratch, result_scratch_root, stage_result_frame
from source_snapshots import quote_column, snapshot_view_ddl, snapshot_view_query, validate_storage_projection


spark = SparkSession.builder.getOrCreate()
catalog = args.catalog
validate_environment(catalog, args.source_catalog, args.target, spark.conf.get("spark.databricks.clusterUsageTags.orgId"))
validate_table_name(args.mapping_table_name, args.target)
suffix = "_dev" if args.target == "D" else ""
plans = json.loads((config_path / "dashboard_results.json").read_text())["datasets"]
if len(plans) != 17 or len({(plan["dashboard"], plan["dataset"]) for plan in plans}) != 17:
    raise ValueError("A unique complete plan is required for all 17 active datasets")
state = f"{catalog}.gold.{RESULT_STATE_TABLE_NAME}{suffix}"
batch = uuid4().hex
marker = "__industry_snapshot_id"
owner = "industry-sales-dashboards"
start = monotonic()


def relation(table, layer="gold"):
    return f"{catalog}.{layer}.`{table}{suffix}`"


def check_owned(name):
    if spark.catalog.tableExists(name):
        properties = {row["key"]: row["value"] for row in spark.sql(f"SHOW TBLPROPERTIES {name}").collect()}
        if properties.get("industry_sales.bundle") != owner:
            raise ValueError(f"Refusing to modify a relation not owned by this bundle: {name}")


def resolve(statement):
    return statement.replace("${var.catalog}", catalog).replace("${var.source_catalog}", args.source_catalog).replace("${var.mapping_table_name}", args.mapping_table_name)


def log(stage, **details):
    print(json.dumps({"stage": stage, "at": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": round(monotonic() - start, 3), **details}), flush=True)


for layer in ("silver", "gold"):
    spark.sql(f"DESCRIBE SCHEMA {catalog}.{layer}").collect()
scratch = result_scratch_root(catalog, args.target, batch)
try:
    scratch.mkdir(parents=True, exist_ok=False)
    probe = stage_result_frame(spark, spark.sql("SELECT CAST(1 AS INT) AS ready"), scratch / "preflight")
    if probe.first()["ready"] != 1:
        raise ValueError("Durable staging readback failed")
    cleanup_result_scratch(scratch / "preflight")
except Exception as error:
    raise RuntimeError(f"Cannot initialize durable staging at {scratch}; the job identity requires READ_VOLUME and WRITE_VOLUME on the existing {catalog}.bronze.bronze_volume") from error
log("scratch_ready", path=str(scratch))
check_owned(state)
tables = list(unique_result_producers(plans))
for table in tables:
    check_owned(relation(table))
    check_owned(relation(result_storage_name(table), "silver"))
spark.sql(
    f"CREATE TABLE IF NOT EXISTS {state} USING DELTA TBLPROPERTIES ('industry_sales.bundle'='industry-sales-dashboards') AS "
    "SELECT CAST(NULL AS STRING) AS snapshot_id, CAST(NULL AS DATE) AS snapshot_as_of_date, "
    "CAST(NULL AS TIMESTAMP) AS snapshot_completed_at, CAST(NULL AS STRING) AS result_receipts WHERE FALSE"
).collect()
old = spark.table(state).collect()
if len(old) > 1:
    raise ValueError("Result state contains multiple active batches")
previous_batch = old[0]["snapshot_id"] if old else None
business_date = spark.sql("SELECT CURRENT_DATE() AS business_date").first()["business_date"]
receipts = []
verified_results = {}


def store_result(table, frame, plan):
    raw = relation(result_storage_name(table), "silver")
    view = relation(table)
    if marker in frame.columns or any("`" in field for field in frame.columns):
        raise ValueError("Invalid or reserved result column")
    row_count = frame.count()
    captured = frame.withColumn(marker, sql_functions.lit(batch))
    if not spark.catalog.tableExists(raw):
        captured.limit(0).createOrReplaceTempView("industry_result_schema")
        spark.sql(f"CREATE TABLE {raw} USING DELTA TBLPROPERTIES ('industry_sales.bundle'='industry-sales-dashboards','delta.columnMapping.mode'='name') AS SELECT * FROM industry_result_schema").collect()
    stored = spark.table(raw).schema
    validate_storage_projection([(field.name, field.dataType) for field in captured.schema.fields], [(field.name, field.dataType) for field in stored.fields])
    if len(stored.fields) != len(captured.schema.fields):
        raise ValueError("Result schema changed; explicit migration required")
    captured.select(*[sql_functions.col(quote_column(field.name)) for field in stored.fields]).write.format("delta").mode("append").saveAsTable(raw)
    actual = spark.table(raw).where(sql_functions.col(marker) == batch).select(*[sql_functions.col(quote_column(field)) for field in frame.columns])
    if frame.exceptAll(actual).limit(1).count() or actual.exceptAll(frame).limit(1).count():
        raise ValueError(f"Result write/read multiset equality failed: {table}")
    spark.sql(snapshot_view_ddl(view, snapshot_view_query(raw, state, frame.columns), spark.catalog.tableExists(view))).collect()
    receipt = {"dashboard": plan["dashboard"], "dataset": plan["dataset"], "table": table, "rows": row_count, "columns": frame.columns}
    receipts.append(receipt)
    verified_results[table] = receipt
    log("result_verified", **receipt)


for plan in plans:
    staged_frames = []
    temporary_views = []
    dataset_scratch = result_dataset_scratch(scratch, plan["dashboard"], plan["dataset"])
    dataset_succeeded = False
    log("dataset_started", dashboard=plan["dashboard"], dataset=plan["dataset"], mode=plan["mode"])
    try:
        for producer in plan["producers"]:
            if producer.get("shared") and producer["table"] in verified_results:
                receipt = dict(verified_results[producer["table"]], dashboard=plan["dashboard"], dataset=plan["dataset"])
                raw = relation(result_storage_name(producer["table"]), "silver")
                result = spark.table(raw).where(sql_functions.col(marker) == batch).select(*[sql_functions.col(quote_column(field)) for field in receipt["columns"]])
                result.createOrReplaceTempView(producer["component"])
                temporary_views.append(producer["component"])
                receipts.append(receipt)
                log("result_reused", **receipt)
                continue
            statement = freeze_sql_date(resolve(producer["sql"]), business_date)
            stages, final = query_parts(statement)
            for name, stage_sql in stages:
                log("compute_started", dataset=plan["dataset"], component=producer["component"], cte=name)
                frame = stage_result_frame(spark, spark.sql(stage_sql), dataset_scratch / str(len(staged_frames)))
                staged_frames.append(frame)
                frame.createOrReplaceTempView(name)
                temporary_views.append(name)
            log("compute_started", dataset=plan["dataset"], component=producer["component"])
            result = stage_result_frame(spark, spark.sql(final), dataset_scratch / str(len(staged_frames)))
            staged_frames.append(result)
            result.createOrReplaceTempView(producer["component"])
            temporary_views.append(producer["component"])
            if producer["table"]:
                store_result(producer["table"], result, plan)
        dataset_succeeded = True
    finally:
        for name in set(temporary_views):
            spark.catalog.dropTempView(name)
        if dataset_succeeded:
            try:
                cleanup_result_scratch(dataset_scratch)
            except Exception as error:
                log("scratch_cleanup_failed", path=str(dataset_scratch), error=str(error))

validate_result_receipts(plans, receipts)
completed = spark.createDataFrame([(batch, business_date, json.dumps(receipts))], "snapshot_id STRING,snapshot_as_of_date DATE,result_receipts STRING").withColumn("snapshot_completed_at", sql_functions.current_timestamp())
completed.createOrReplaceTempView("industry_completed_result_batch")
spark.sql(f"CREATE OR REPLACE TABLE {state} USING DELTA TBLPROPERTIES ('industry_sales.bundle'='industry-sales-dashboards') AS SELECT snapshot_id,snapshot_as_of_date,snapshot_completed_at,result_receipts FROM industry_completed_result_batch").collect()
log("published", snapshot_id=batch, business_date=business_date.isoformat(), datasets=len(plans), result_relations=len(tables))
retained = [batch] + ([previous_batch] if previous_batch else [])
keep = ",".join("'" + value + "'" for value in retained)
for table in tables:
    raw = relation(result_storage_name(table), "silver")
    spark.sql(f"DELETE FROM {raw} WHERE `{marker}` NOT IN ({keep})").collect()
try:
    cleanup_result_scratch(scratch)
except Exception as error:
    log("scratch_cleanup_failed", path=str(scratch), error=str(error))