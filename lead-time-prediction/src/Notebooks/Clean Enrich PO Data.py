# Databricks notebook source
# DBTITLE 1,Config
# MAGIC %md
# MAGIC # Silver — Clean & Enrich PO Data
# MAGIC Reads `bronze.lead_time_po_raw`, applies all transformations, writes `silver.lead_time_po_clean`.

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./config_file
# MAGIC

# COMMAND ----------

# DBTITLE 1,Imports
from pyspark.sql import functions as F

# COMMAND ----------

# DBTITLE 1,Transform Bronze → Silver
# ── Read Bronze ─────────────────────────────────────────────────────
df_bronze = spark.table(f"{BRONZE}.lead_time_po_raw")

# ── Transformations ─────────────────────────────────────────────────────
df_silver = (
    df_bronze
    # Extract plant code from "CODE - Description" text
    .withColumn("plant_code", F.split(F.col("plant_code_text"), " - ").getItem(0))
    # Rename raw date column
    .withColumnRenamed("date_gr", "goods_receipt_date")
    # Build composite PO number: po_number-po_item
    .withColumn(
        "po_number",
        F.concat_ws("-", F.col("po_number").cast("string"), F.col("po_item").cast("string"))
    )
    # Compute expected delivery date from PO creation + planned lead time
    .withColumn(
        "req_delivery_date",
        F.when(
            F.col("planned_delivery_time").isNotNull(),
            F.date_add(F.col("po_creation_date"), F.col("planned_delivery_time").cast("int"))
        )
    )
    # Align column name with downstream usage
    .withColumnRenamed("material_id", "material_code")
    # Final column selection
    .select(
        "vendor_key", "plant_key", "material_key", "material_plant_key",
        "plant_code", "vendor_id", "material_code",
        "po_number", "po_creation_date", "goods_receipt_date", "req_delivery_date"
    )
)

# ── Vendor filter: keep only vendors with at least one order ──────────────────
vendor_df = (
    df_silver
    .filter(F.col("vendor_id").isNotNull())
    .groupBy("vendor_id")
    .agg(F.countDistinct("po_number").alias("orders_vendor"))
)
df_silver = df_silver.join(vendor_df.select("vendor_id"), "vendor_id", "inner")

# COMMAND ----------

# DBTITLE 1,Write to Silver
df_silver.write \
    .format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(f"{SILVER}.lead_time_po_clean")

print(f"Silver written → {SILVER}.lead_time_po_clean")
