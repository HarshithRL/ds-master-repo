# Databricks notebook source
import re
from datetime import datetime
from functools import reduce

from pyspark.sql import functions as F
from pyspark.sql.window import Window


dbutils.widgets.text("catalog", "automation_d")
dbutils.widgets.text("historical_as_of_date", "2026-10-08")

CATALOG = dbutils.widgets.get("catalog").strip()
HISTORICAL_AS_OF_DATE = dbutils.widgets.get("historical_as_of_date").strip()

if not re.fullmatch(r"[a-z][a-z0-9_]*", CATALOG):
    raise ValueError(f"Invalid catalog name: {CATALOG!r}")

try:
    datetime.strptime(HISTORICAL_AS_OF_DATE, "%Y-%m-%d")
except ValueError as error:
    raise ValueError("historical_as_of_date must use YYYY-MM-DD.") from error

for schema in ("bronze", "silver", "gold"):
    spark.sql(f"DESCRIBE SCHEMA {CATALOG}.{schema}")

VOLUME_BASE = f"/Volumes/{CATALOG}/bronze/bronze_volume/Copilot_Dashboard_Data"
HISTORICAL_DIRECTORY = f"{VOLUME_BASE}_Historical/Copilot Credit Consumption"
HISTORICAL_WINDOWS = (30, 60, 90, 180)
HISTORICAL_TABLE = f"{CATALOG}.gold.copilot_credit_historical_periods"
LIVE_TABLE = f"{CATALOG}.gold.copilot_credit_live_snapshots"


def parse_credit_column(column_name):
    raw_value = F.trim(F.col(column_name))
    return F.when(
        raw_value.isNull() | (raw_value == ""),
        F.lit(0.0),
    ).otherwise(
        F.regexp_replace(raw_value, ",", "").cast("double")
    )


def aggregate_credit_file(file_path):
    raw = spark.read.option("header", "true").option("mode", "FAILFAST").csv(file_path)
    required_columns = {"Billed credit", "Non-billed credit"}
    missing_columns = required_columns.difference(raw.columns)
    if missing_columns:
        raise RuntimeError(f"{file_path} is missing columns: {sorted(missing_columns)}")

    parsed = (
        raw.withColumn("billed_credit", parse_credit_column("Billed credit"))
        .withColumn("non_billed_credit", parse_credit_column("Non-billed credit"))
    )
    invalid_rows = parsed.filter(
        (
            F.trim(F.col("Billed credit")).isNotNull()
            & (F.trim(F.col("Billed credit")) != "")
            & F.col("billed_credit").isNull()
        )
        | (
            F.trim(F.col("Non-billed credit")).isNotNull()
            & (F.trim(F.col("Non-billed credit")) != "")
            & F.col("non_billed_credit").isNull()
        )
    ).count()
    if invalid_rows:
        raise RuntimeError(f"{file_path} has {invalid_rows} rows with invalid credit values.")

    return parsed.agg(
        F.count(F.lit(1)).alias("source_rows"),
        F.sum("billed_credit").alias("billed_credits"),
        F.sum("non_billed_credit").alias("non_billed_credits"),
    ).select(
        "source_rows",
        F.coalesce(F.col("billed_credits"), F.lit(0.0)).alias("billed_credits"),
        F.coalesce(F.col("non_billed_credits"), F.lit(0.0)).alias("non_billed_credits"),
    )


historical_snapshots = []
for window_days in HISTORICAL_WINDOWS:
    historical_path = f"{HISTORICAL_DIRECTORY}/Agent-Level Credit Consumption -{window_days} days.csv"
    historical_snapshots.append(
        aggregate_credit_file(historical_path).withColumn("window_days", F.lit(window_days))
    )

historical_cumulative = reduce(lambda left, right: left.unionByName(right), historical_snapshots)
window_spec = Window.orderBy("window_days")
historical_periods = (
    historical_cumulative.withColumn("previous_window_days", F.lag("window_days").over(window_spec))
    .withColumn("previous_billed_credits", F.lag("billed_credits").over(window_spec))
    .withColumn("previous_non_billed_credits", F.lag("non_billed_credits").over(window_spec))
    .withColumn(
        "billed_credits",
        F.col("billed_credits") - F.coalesce(F.col("previous_billed_credits"), F.lit(0.0)),
    )
    .withColumn(
        "non_billed_credits",
        F.col("non_billed_credits") - F.coalesce(F.col("previous_non_billed_credits"), F.lit(0.0)),
    )
    .withColumn(
        "period_days",
        F.col("window_days") - F.coalesce(F.col("previous_window_days"), F.lit(0)),
    )
)

negative_deltas = historical_periods.filter(
    (F.col("billed_credits") < 0) | (F.col("non_billed_credits") < 0)
).count()
if negative_deltas:
    raise RuntimeError(
        "Historical rolling-window extracts are not cumulative: one or more difference periods are negative."
    )

credit_rate_row = (
    spark.table(f"{CATALOG}.silver.ref_credit_rate")
    .filter(F.upper(F.col("currency")) == "EUR")
    .agg(F.max(F.col("credit_to_eur")).alias("credit_to_eur"))
    .first()
)
credit_to_eur = credit_rate_row["credit_to_eur"]
if credit_to_eur is None or float(credit_to_eur) <= 0:
    raise RuntimeError(f"{CATALOG}.silver.ref_credit_rate does not provide a positive EUR credit rate.")

historical_as_of = F.lit(HISTORICAL_AS_OF_DATE).cast("date")
historical_periods = (
    historical_periods.withColumn("snapshot_as_of_date", historical_as_of)
    .withColumn("period_start_date", F.date_sub(historical_as_of, F.col("window_days") - 1))
    .withColumn(
        "period_end_date",
        F.date_sub(historical_as_of, F.coalesce(F.col("previous_window_days"), F.lit(0))),
    )
    .withColumn(
        "period_label",
        F.concat(
            F.lit("Days "),
            F.coalesce(F.col("previous_window_days"), F.lit(0)) + 1,
            F.lit("-"),
            F.col("window_days"),
        ),
    )
    .withColumn("total_credits", F.col("billed_credits") + F.col("non_billed_credits"))
    .withColumn("credit_to_eur", F.lit(float(credit_to_eur)))
    .withColumn("billed_cost_eur", F.col("billed_credits") * F.col("credit_to_eur"))
    .withColumn("non_billed_cost_eur", F.col("non_billed_credits") * F.col("credit_to_eur"))
    .withColumn("total_cost_eur", F.col("total_credits") * F.col("credit_to_eur"))
    .withColumn("source_type", F.lit("HISTORICAL_CUMULATIVE_WINDOW_DIFFERENCE"))
    .withColumn("refreshed_at", F.current_timestamp())
    .select(
        "snapshot_as_of_date",
        "period_start_date",
        "period_end_date",
        "period_label",
        "period_days",
        "window_days",
        "source_rows",
        "billed_credits",
        "non_billed_credits",
        "total_credits",
        "credit_to_eur",
        "billed_cost_eur",
        "non_billed_cost_eur",
        "total_cost_eur",
        "source_type",
        "refreshed_at",
    )
)

live_snapshots = []
for file_info in dbutils.fs.ls(VOLUME_BASE):
    folder_name = file_info.name.rstrip("/")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}", folder_name):
        continue
    snapshot_path = f"{VOLUME_BASE}/{folder_name}/agent_level_credit_consumption.csv"
    try:
        dbutils.fs.ls(snapshot_path)
    except Exception:
        continue
    snapshot_time = datetime.strptime(folder_name, "%Y-%m-%d_%H-%M-%S")
    live_snapshots.append(
        aggregate_credit_file(snapshot_path)
        .withColumn("snapshot_timestamp", F.lit(snapshot_time).cast("timestamp"))
        .withColumn("snapshot_date", F.lit(snapshot_time.date()).cast("date"))
    )

if not live_snapshots:
    raise RuntimeError(f"No agent-level credit snapshots were found under {VOLUME_BASE}.")

live_history = reduce(lambda left, right: left.unionByName(right), live_snapshots)
latest_snapshot_per_day = Window.partitionBy("snapshot_date").orderBy(F.col("snapshot_timestamp").desc())
live_history = (
    live_history.withColumn("snapshot_rank", F.row_number().over(latest_snapshot_per_day))
    .filter(F.col("snapshot_rank") == 1)
    .drop("snapshot_rank")
    .withColumn("rolling_window_days", F.lit(30))
    .withColumn("total_credits", F.col("billed_credits") + F.col("non_billed_credits"))
    .withColumn("credit_to_eur", F.lit(float(credit_to_eur)))
    .withColumn("billed_cost_eur", F.col("billed_credits") * F.col("credit_to_eur"))
    .withColumn("non_billed_cost_eur", F.col("non_billed_credits") * F.col("credit_to_eur"))
    .withColumn("total_cost_eur", F.col("total_credits") * F.col("credit_to_eur"))
    .withColumn("source_type", F.lit("LIVE_ROLLING_30_DAY_SNAPSHOT"))
    .withColumn("refreshed_at", F.current_timestamp())
    .select(
        "snapshot_timestamp",
        "snapshot_date",
        "rolling_window_days",
        "source_rows",
        "billed_credits",
        "non_billed_credits",
        "total_credits",
        "credit_to_eur",
        "billed_cost_eur",
        "non_billed_cost_eur",
        "total_cost_eur",
        "source_type",
        "refreshed_at",
    )
)

historical_periods.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(HISTORICAL_TABLE)
live_history.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(LIVE_TABLE)

print(f"Published {historical_periods.count()} historical credit periods to {HISTORICAL_TABLE}.")
print(f"Published {live_history.count()} rolling 30-day snapshots to {LIVE_TABLE}.")
