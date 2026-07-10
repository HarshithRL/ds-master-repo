# Databricks notebook source
# =============================================================================
# SILVER: Clean and enrich data
# =============================================================================
# Demonstrates: reading bronze, applying transformations, writing to silver.
# In real projects, add deduplication, data quality checks, type casting, etc.
# =============================================================================

# MAGIC %run ./config_file

# COMMAND ----------

from pyspark.sql import functions as F

# ── Read bronze ──────────────────────────────────────────────────
df = spark.table(bronze_table("hello_world_raw"))

# COMMAND ----------

# ── Transform ────────────────────────────────────────────────────
df_clean = (
    df
    # Cast hire_date string to proper date type
    .withColumn("hire_date", F.to_date("hire_date", "yyyy-MM-dd"))
    # Compute tenure in years
    .withColumn("tenure_years", F.round(F.datediff(F.current_date(), "hire_date") / 365.25, 1))
    # Standardize department names
    .withColumn("department", F.upper(F.col("department")))
    # Drop ingestion metadata (not needed in silver)
    .drop("_ingested_at")
    # Add processing timestamp
    .withColumn("_processed_at", F.current_timestamp())
)

# COMMAND ----------

# ── Write to silver ──────────────────────────────────────────────
target = silver_table("hello_world_clean")
df_clean.write.saveAsTable(target)

print(f"Silver table written: {target}")
df_clean.display()
