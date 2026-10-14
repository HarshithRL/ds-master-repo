import argparse
import json
import sys
from pathlib import Path

from pyspark import StorageLevel
from pyspark.sql import SparkSession, functions as sql_functions


parser = argparse.ArgumentParser()
parser.add_argument("--catalog", required=True)
parser.add_argument("--source-catalog", required=True)
parser.add_argument("--target", required=True)
parser.add_argument("--mapping-table-name", required=True)
parser.add_argument("--config-path", required=True)
parser.add_argument("--candidate", action="store_true")
args = parser.parse_args()
spark = SparkSession.builder.getOrCreate()
catalog = args.catalog
source_catalog = args.source_catalog
target = args.target
mapping_table_name = args.mapping_table_name
config_path = Path(args.config_path)
sys.path.insert(0, str(config_path.parent))

from allocation_stages import build_stages, output_table_name
from industry_config import validate_environment, validate_table_name
from source_snapshots import SNAPSHOT_PREFIX, pinned_snapshot_query, validate_complete_receipts, validate_manifest


validate_environment(catalog, source_catalog, target, spark.conf.get("spark.databricks.clusterUsageTags.orgId"))
validate_table_name(mapping_table_name, target)
spark.sql(f"DESCRIBE SCHEMA {catalog}.gold").collect()
source = (config_path / "open_orders_allocation.sql").read_text()
source_suffix = "_dev" if target == "D" else ""
source = source.replace("${var.catalog}", catalog).replace("${var.mapping_table_name}", mapping_table_name).replace("${var.source_snapshot_suffix}", source_suffix)
source_state = spark.table(f"{catalog}.gold.industry_sales_source_snapshot_state{source_suffix}").collect()
if len(source_state) != 1 or not source_state[0]["snapshot_id"]:
    raise ValueError("A complete local source snapshot is required before allocation")
as_of_date = source_state[0]["snapshot_as_of_date"]
snapshot_sources = validate_manifest(json.loads((config_path / "source_snapshots.json").read_text())["sources"])
source_receipts = json.loads(source_state[0]["source_receipts"])
validate_complete_receipts(snapshot_sources, source_receipts)
pinned_views = []
for input_source in snapshot_sources:
    receipt = next(item for item in source_receipts if item["source"] == input_source["source_table"])
    raw = f"{catalog}.bronze.`{input_source['snapshot_table'].replace(SNAPSHOT_PREFIX, 'industry_sales_raw_', 1)}{source_suffix}`"
    view_name = input_source["snapshot_table"] + source_suffix
    spark.sql(pinned_snapshot_query(raw, source_state[0]["snapshot_id"], receipt["columns"])).createOrReplaceTempView(view_name)
    pinned_views.append(view_name)
    source = source.replace(f"`{catalog}`.silver.`{view_name}`", f"`{view_name}`")
destination = f"{catalog}.gold.{output_table_name(mapping_table_name)}"
if args.candidate:
    destination += "_candidate"
if spark.catalog.tableExists(destination):
    properties = {row["key"]: row["value"] for row in spark.sql(f"SHOW TBLPROPERTIES {destination}").collect()}
    if properties.get("industry_sales.bundle") != "industry-sales-dashboards":
        raise ValueError(f"Refusing to replace a table not owned by this bundle: {destination}")

stages, final_query = build_stages(source, as_of_date)
cached = []
stage_receipts = []
output = None
try:
    for name, statement in stages:
        frame = spark.sql(statement).localCheckpoint(eager=True)
        cached.append((name, frame))
        row_count = frame.count()
        frame.createOrReplaceTempView(name)
        stage_receipts.append({"stage": name, "rows": row_count})
        print(json.dumps(stage_receipts[-1]), flush=True)
    output = spark.sql(final_query).persist(StorageLevel.DISK_ONLY)
    expected_columns = ("scope", "cs_team", "segment", "plant", "bucket", "value_eur")
    if tuple(output.columns) != expected_columns:
        raise ValueError(f"Unexpected allocation output columns: {output.columns}")
    row_count = output.count()
    if row_count == 0:
        raise ValueError("Allocation output is empty; refusing to replace existing gold data")
    if spark.table(f"{catalog}.gold.industry_sales_source_snapshot_state{source_suffix}").first()["snapshot_id"] != source_state[0]["snapshot_id"]:
        raise ValueError("Source snapshot changed during allocation; refusing to publish a mixed result")
    published = output.withColumn("allocation_as_of_date", sql_functions.lit(as_of_date)).withColumn("allocation_refreshed_at", sql_functions.current_timestamp()).withColumn("source_snapshot_id", sql_functions.lit(source_state[0]["snapshot_id"]))
    published.createOrReplaceTempView("industry_allocation_publish")
    spark.sql(
        f"CREATE OR REPLACE TABLE {destination} USING DELTA "
        "TBLPROPERTIES ('industry_sales.bundle'='industry-sales-dashboards') "
        "AS SELECT * FROM industry_allocation_publish"
    ).collect()
    actual = spark.table(destination).select(*expected_columns)
    if output.exceptAll(actual).limit(1).count() or actual.exceptAll(output).limit(1).count():
        raise ValueError("Allocation gold write/read parity failed")
    print(json.dumps({"table": destination, "rows": row_count, "business_date": as_of_date.isoformat(), "stages": stage_receipts}), flush=True)
finally:
    if output is not None:
        output.unpersist()
    for name, frame in reversed(cached):
        spark.catalog.dropTempView(name)
        frame.unpersist()
    for name in pinned_views:
        spark.catalog.dropTempView(name)