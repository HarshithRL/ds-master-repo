# Databricks notebook source
import json
import sys
from pathlib import Path

from pyspark.sql.types import StringType, StructField, StructType


dbutils.widgets.text("catalog", "")
dbutils.widgets.text("source_catalog", "")
dbutils.widgets.text("config_path", "")
dbutils.widgets.text("target", "")
dbutils.widgets.text("mapping_table_name", "")

catalog = dbutils.widgets.get("catalog")
source_catalog = dbutils.widgets.get("source_catalog")
target = dbutils.widgets.get("target")
config_path = Path(dbutils.widgets.get("config_path"))
sys.path.insert(0, str(config_path.parent))

from industry_config import MAPPING_COLUMNS, validate_environment, validate_mapping, validate_table_name


workspace_id = spark.conf.get("spark.databricks.clusterUsageTags.orgId")
validate_environment(catalog, source_catalog, target, workspace_id)
table_name = dbutils.widgets.get("mapping_table_name")
validate_table_name(table_name, target)
seed = json.loads((config_path / "cs_team_sales_org_mapping.json").read_text())
rows = validate_mapping(seed["rows"])
dependencies = json.loads((config_path / "source_dependencies.json").read_text())

for layer in ("bronze", "silver", "gold"):
    spark.sql(f"DESCRIBE SCHEMA {catalog}.{layer}").collect()

for source_table_name in dependencies["pbi_tables"]:
    if "`" in source_table_name:
        raise ValueError(f"Invalid source table: {source_table_name!r}")
    spark.sql(f"SELECT * FROM `{source_catalog}`.pbi.`{source_table_name}` LIMIT 0").collect()

destinations = [f"{catalog}.{layer}.{table_name}" for layer in ("bronze", "silver", "gold")]
for destination in destinations:
    if spark.catalog.tableExists(destination):
        properties = {
            property_row["key"]: property_row["value"]
            for property_row in spark.sql(f"SHOW TBLPROPERTIES {destination}").collect()
        }
        if properties.get("industry_sales.bundle") != "industry-sales-dashboards":
            raise ValueError(f"Refusing to replace a table not owned by this bundle: {destination}")

schema = StructType([StructField(column, StringType(), False) for column in MAPPING_COLUMNS])
expected = spark.createDataFrame(rows, schema)
expected.createOrReplaceTempView("industry_sales_mapping_seed")
columns = ", ".join(MAPPING_COLUMNS)
previous = "industry_sales_mapping_seed"
for destination in destinations:
    spark.sql(
        f"CREATE OR REPLACE TABLE {destination} USING DELTA "
        "TBLPROPERTIES ('industry_sales.bundle' = 'industry-sales-dashboards') "
        f"AS SELECT {columns} FROM {previous}"
    ).collect()
    actual = spark.table(destination).select(*MAPPING_COLUMNS)
    if expected.exceptAll(actual).limit(1).count() or actual.exceptAll(expected).limit(1).count():
        raise ValueError(f"Mapping write/read parity failed: {destination}")
    previous = destination

print(f"Validated {len(dependencies['pbi_tables'])} sources; published {len(rows)} unchanged mapping rows to {catalog}.gold")