# Databricks notebook source
# DBTITLE 1,Imports
from pyspark.sql import functions as F

# COMMAND ----------

# MAGIC %run ./config_file

# COMMAND ----------

# DBTITLE 1,Lookback config
LOOKBACK_MONTHS = 36

# COMMAND ----------

# MAGIC %md
# MAGIC ## MDP Tables

# COMMAND ----------

# DBTITLE 1,Build and join MDP tables
# -----------------------------
# CONFIG + TABLES
# -----------------------------
# SYNAPSE_CATALOG and SYNAPSE_SCHEMA are set by config_file

def t(name: str) -> str:
    return f"{SYNAPSE_CATALOG}.{SYNAPSE_SCHEMA}.{name}"

FACT      = t("dbx_fact_purchasing_document_summary")
DIM_MATP  = t("dbx_dim_material_plant")
DIM_VEND  = t("dbx_dim_vendor")
DIM_PLANT = t("dbx_dim_plant")

RUN_DATE = F.current_date()
MIN_DATE = F.add_months(RUN_DATE, -LOOKBACK_MONTHS)

fact      = spark.table(FACT)
dim_matp  = spark.table(DIM_MATP)
dim_vend  = spark.table(DIM_VEND)
dim_plant = spark.table(DIM_PLANT)

# -----------------------------
# BASE FACT (SAFE DATE PARSING)
# -----------------------------

base = (
    fact.select(
        F.col("Purchasing Document Number").alias("po_number"),
        F.col("Purchasing Document Item Number").alias("po_item"),
        F.col("Plant Key").alias("plant_key"),
        F.col("Company Key").alias("company_key"),
        F.col("Material Key").alias("material_key"),
        F.col("Material Plant Key").alias("material_plant_key"),
        F.col("Supplier Key").alias("vendor_key"),

        F.col("Date Document").alias("po_creation_date_raw"),
        F.col("Date Goods Receipt").alias("date_gr_raw"),

        F.to_date(F.col("Date Document").cast("string"), "yyyy-MM-dd").alias("po_creation_date"),
        F.to_date(F.col("Date Goods Receipt").cast("string"), "yyyy-MM-dd").alias("date_gr"),

        F.col("Measure Quantity Order Quantity").cast("double").alias("po_qty"),
        F.col("Goods receipt Indicator").alias("gr_indicator"),
    )
)
base_last36m = base.filter(F.col("po_creation_date").isNotNull()).filter(F.col("po_creation_date") >= MIN_DATE)

# -----------------------------
# DIMENSIONS (only needed cols)
# -----------------------------
dim_plant_s = (
    dim_plant.select(
        F.col("Plant Key").alias("plant_key"),
        F.col("Plant Code").alias("plant_code"),
        F.col("Plant Text").alias("plant_text"),
        F.col("Country").alias("country"),
        F.col("Company Code").alias("company"),
    )
    .withColumn("plant_code_text", F.concat_ws(" - ", F.col("plant_code"), F.col("plant_text")))
    .select("plant_key", "country", "company", "plant_code_text")
)

dim_vend_s = dim_vend.select(
    F.col("Vendor Key").alias("vendor_key"),
    F.col("Vendor Id").alias("vendor_id"),
    F.col("Vendor Name").alias("vendor_name"),
)

dim_matp_s = dim_matp.select(
    F.col("Material Plant Key").alias("material_plant_key"),
    F.col("Material Id").alias("material_id"),
    F.col("Text").alias("material_description"),
    F.col("Planned Deliv Time").cast("double").alias("planned_delivery_time"),
)


# -----------------------------
# JOIN
# -----------------------------
df = (
    base_last36m
    .join(dim_matp_s,  "material_plant_key", "left")
    .join(dim_plant_s, "plant_key", "left")
    .join(dim_vend_s,  "vendor_key", "left")
)

# -----------------------------
# FINAL SELECT
# -----------------------------
out = df.select(
    "country",
    "company",
    "plant_code_text",
    "po_number",
    "po_item",
    "vendor_key",
    "vendor_id",
    "vendor_name",
    "plant_key",
    "material_key",
    "material_plant_key",
    "material_id",
    "material_description",
    "po_creation_date",
    "date_gr",
    "po_qty",
    "gr_indicator",
    "planned_delivery_time",

    "po_creation_date_raw",
    "date_gr_raw",
)

out_filtered = out.filter(
    (F.col("plant_code_text").isNotNull()) &
    (F.col("vendor_id").isNotNull()) &
    (F.col("material_id").isNotNull()) &
    (~F.col("material_id").like("UNKNOWN"))
)

# COMMAND ----------

# DBTITLE 1,Debug check
# display(out_filtered.filter(F.col("material_id").endswith("6705520")))

# COMMAND ----------

# DBTITLE 1,Write to Bronze
out_filtered.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{BRONZE}.lead_time_po_raw")
print(f"Bronze written → {BRONZE}.lead_time_po_raw")

# COMMAND ----------


