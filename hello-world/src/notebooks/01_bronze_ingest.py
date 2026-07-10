# Databricks notebook source
# =============================================================================
# BRONZE: Ingest raw sample data
# =============================================================================
# Demonstrates: creating a raw table from a simple data source.
# In real projects, replace this with ingestion from ADLS, Synapse, APIs, etc.
# =============================================================================

# MAGIC %run ./config_file

# COMMAND ----------

# ── Generate sample raw data ─────────────────────────────────────
from pyspark.sql import functions as F

raw_data = spark.createDataFrame(
    [
        ("Alice", "Engineering", 85000, "2022-01-15"),
        ("Bob", "Marketing", 72000, "2021-06-01"),
        ("Charlie", "Engineering", 92000, "2023-03-20"),
        ("Diana", "Sales", 68000, "2020-11-10"),
        ("Eve", "Marketing", 77000, "2022-08-05"),
        ("Frank", "Engineering", 105000, "2019-04-22"),
        ("Grace", "Sales", 71000, "2023-01-08"),
        ("Hank", "Engineering", 88000, "2021-12-01"),
    ],
    schema=["name", "department", "salary", "hire_date"],
)

# Add ingestion metadata
raw_data = raw_data.withColumn("_ingested_at", F.current_timestamp())

# COMMAND ----------

# ── Write to bronze ──────────────────────────────────────────────
# NOTE: In production, use mode("overwrite") or merge logic as appropriate.
target = bronze_table("hello_world_raw")
raw_data.write.saveAsTable(target)

print(f"Bronze table written: {target}")
spark.table(target).display()
