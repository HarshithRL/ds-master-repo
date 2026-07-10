# Databricks notebook source
# =============================================================================
# GOLD: Business aggregates
# =============================================================================
# Demonstrates: reading silver, computing business metrics, writing to gold.
# In real projects, this might produce KPI tables, ML predictions, or reports.
# =============================================================================

# MAGIC %run ./config_file

# COMMAND ----------

from pyspark.sql import functions as F

# ── Read silver ──────────────────────────────────────────────────
df = spark.table(silver_table("hello_world_clean"))

# COMMAND ----------

# ── Aggregate: department summary ────────────────────────────────
dept_summary = (
    df
    .groupBy("department")
    .agg(
        F.count("*").alias("headcount"),
        F.round(F.avg("salary"), 0).alias("avg_salary"),
        F.round(F.avg("tenure_years"), 1).alias("avg_tenure_years"),
        F.min("hire_date").alias("earliest_hire"),
        F.max("hire_date").alias("latest_hire"),
    )
    .withColumn("_computed_at", F.current_timestamp())
)

# COMMAND ----------

# ── Write to gold ────────────────────────────────────────────────
target = gold_table("hello_world_summary")
dept_summary.write.saveAsTable(target)

print(f"Gold table written: {target}")
dept_summary.display()
