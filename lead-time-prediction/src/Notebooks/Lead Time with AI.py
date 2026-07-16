# Databricks notebook source
# MAGIC %md
# MAGIC # Config

# COMMAND ----------

# MAGIC %run ./config_file

# COMMAND ----------

# DBTITLE 1,Data sources
# Input : silver layer — cleaned & enriched PO data
# Output: gold layer  — forecasts + supplier reliability tables
SILVER_INPUT = f"{SILVER}.lead_time_po_clean"

# COMMAND ----------

# MAGIC %md
# MAGIC # Libraries

# COMMAND ----------

from __future__ import annotations

import re
from datetime import date
import time

from typing import Dict, List, Optional

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from pyspark.ml import Pipeline
from pyspark.ml.feature import StringIndexer, OneHotEncoder, VectorAssembler
from pyspark.ml.regression import LinearRegression, GBTRegressor

import itertools, mlflow

import plotly.express as px

from pyspark.storagelevel import StorageLevel
from pyspark.ml.functions import vector_to_array


# COMMAND ----------

# MAGIC %md
# MAGIC # Load Data
# MAGIC

# COMMAND ----------

# MAGIC %md
# MAGIC ## MDP Data

# COMMAND ----------

# MAGIC %md
# MAGIC ### Load from Silver

# COMMAND ----------

# DBTITLE 1,Load from Silver
# All cleaning & enrichment is handled by the Silver notebook.
# This notebook reads the ready-to-use silver table directly.
df0 = spark.table(SILVER_INPUT)


# COMMAND ----------

# MAGIC %md
# MAGIC # Modelling

# COMMAND ----------

# MAGIC %md
# MAGIC ## ML Approach

# COMMAND ----------

# # ============================================================
# # END-TO-END: SIMPLE 3-BUCKET MVP (PVM+MOY + Residual ML + PVM fallback)
# # + fixes for:
# #   - remove invalid keys (-1)
# #   - leakage-safe feature tables for holdout eval (built from TRAIN only)
# #   - null-safe eval metrics (no more null mae/medae)
# #   - optional debug table: actual vs predicted on holdout
# #
# # BUCKET LADDER (unchanged intent):
# #   1) ML_FROM_PVM_MOY            if pvm_moy_sufficient 
# #   2) NO_ML__PVM_MOY_Median      if p50_pvm_moy exists but n_pvm_moy < MIN_OBS_PVM_MOY 
# #   3) NO_ML__PVM_Median          otherwise 
# # ============================================================

# import time
# from typing import List, Tuple, Optional, Dict

# import pyspark.sql.functions as F
# from pyspark.sql import DataFrame
# from pyspark.storagelevel import StorageLevel

# from pyspark.ml import Pipeline
# from pyspark.ml.feature import VectorAssembler
# from pyspark.ml.regression import LinearRegression, GBTRegressor

# # =======================
# # CONFIG
# # =======================
# RUN_DATE = F.current_date()              # or F.lit("2026-02-04").cast("date")
# HOLDOUT_DAYS = 90

# ACC = 50
# MIN_LT_DAYS = 1
# MAX_LT_DAYS = 365
# MIN_TRAIN_ROWS = 1000

# # Outliers (MAD z-score)
# OUTLIER_Z = 3.5
# MIN_N_FOR_MAD_KEY = 10
# MIN_N_FOR_MAD_VENDOR_MAT = 20
# MIN_N_FOR_MAD_VENDOR = 50

# # ML
# USE_RESIDUAL_ML = True
# RESIDUAL_MODEL = "lr"                  # "lr" or "gbt"
# SEED = 42

# # Eligibility threshold for ML at PVM_MOY
# MIN_OBS_PVM_MOY = 10

# # For std in "moy across years" KPI
# MIN_OBS_CURRENT_MOY = 5

# # Guardrails (highly recommended to avoid insane residuals)
# RESID_CLAMP_DAYS = 60.0                 # hard clamp residual prediction (days)

# # Performance
# SHUFFLE_PARTITIONS = 64
# AUTO_BROADCAST_BYTES = 104857600
# BROADCAST_TIMEOUT_SEC = 1200

# spark.conf.set("spark.sql.shuffle.partitions", str(SHUFFLE_PARTITIONS))
# spark.conf.set("spark.sql.adaptive.enabled", "true")
# spark.conf.set("spark.sql.autoBroadcastJoinThreshold", str(AUTO_BROADCAST_BYTES))
# spark.conf.set("spark.sql.broadcastTimeout", str(BROADCAST_TIMEOUT_SEC))

# keys = ["plant_code", "vendor_id", "material_code"]
# pv_keys = ["plant_code", "vendor_id"]

# # =======================
# # UTIL
# # =======================
# def log_step(msg: str, extra: str = ""):
#     ts = time.strftime("%Y-%m-%d %H:%M:%S")
#     print(f"[{ts}] {msg}" + (f" | {extra}" if extra else ""))

# def clamp_days(c):
#     return F.when(c.isNull(), None).otherwise(F.greatest(F.lit(float(MIN_LT_DAYS)), F.least(c, F.lit(float(MAX_LT_DAYS)))))

# def clamp_resid(c):
#     return F.greatest(F.lit(-float(RESID_CLAMP_DAYS)), F.least(c, F.lit(float(RESID_CLAMP_DAYS))))

# def to_finite(col, fill_val=0.0):
#     c = col.cast("double")
#     finite = c.isNotNull() & (~F.isnan(c)) & (c != F.lit(float("inf"))) & (c != F.lit(float("-inf")))
#     return F.when(finite, c).otherwise(F.lit(fill_val).cast("double"))

# def split_time(df: DataFrame, holdout_days: int) -> Tuple[DataFrame, DataFrame]:
#     holdout_start = F.date_sub(RUN_DATE, holdout_days)
#     return (
#         df.filter(F.col("po_creation_date") < holdout_start),
#         df.filter(F.col("po_creation_date") >= holdout_start),
#     )

# def add_seasonality(df: DataFrame) -> DataFrame:
#     return (
#         df.withColumn("moy_sin", F.sin(2 * F.pi() * F.col("moy") / F.lit(12.0)))
#           .withColumn("moy_cos", F.cos(2 * F.pi() * F.col("moy") / F.lit(12.0)))
#     )

# def is_unknown_material_expr(colname="material_code"):
#     c = F.col(colname)
#     return (
#         c.isNull() |
#         (F.length(F.trim(c)) == 0) |
#         (F.upper(F.trim(c)).isin("UNKNOWN", "UNK", "N/A", "NA", "NULL"))
#     )

# def mae(col_y, col_yhat):
#     return F.avg(F.abs(F.col(col_y) - F.col(col_yhat))).alias("mae")

# def medae(col_y, col_yhat):
#     return F.expr(f"percentile_approx(abs({col_y} - {col_yhat}), 0.5)").cast("double").alias("medae")

# def rmse(col_y, col_yhat):
#     return F.sqrt(F.avg(F.pow(F.col(col_y) - F.col(col_yhat), 2))).alias("rmse")

# # =======================
# # 1) BUILD df_item + df_done (and remove invalid keys early)
# # =======================
# INVALID_KEY_STR = "-1"

# df_item = (
#     df0
#     .select(
#         F.col("po_creation_date").cast("date").alias("po_creation_date"),
#         F.col("plant_code").cast("string").alias("plant_code"),
#         F.col("vendor_id").cast("string").alias("vendor_id"),
#         F.col("material_code").cast("string").alias("material_code"),
#         F.col("goods_receipt_date").cast("date").alias("goods_receipt_date"),
#         F.col("req_delivery_date").cast("date").alias("req_delivery_date"),
#         F.col("po_number").cast("string").alias("po_number"),
#     )
#     .filter(F.col("po_creation_date").isNotNull())
#     # remove invalid keys (-1, null)
#     .filter(
#         F.col("plant_code").isNotNull() & F.col("vendor_id").isNotNull() & F.col("material_code").isNotNull() &
#         (F.col("plant_code") != F.lit(INVALID_KEY_STR)) &
#         (F.col("vendor_id") != F.lit(INVALID_KEY_STR)) &
#         (F.col("material_code") != F.lit(INVALID_KEY_STR))
#     )
#     .withColumn("missing_gr", F.col("goods_receipt_date").isNull().cast("int"))
#     .withColumn("missing_req", F.col("req_delivery_date").isNull().cast("int"))
#     .withColumn(
#         "planned_deliv_time",
#         F.when(
#             F.col("req_delivery_date").isNotNull(),
#             F.datediff("req_delivery_date", "po_creation_date").cast("double")
#         ).otherwise(F.lit(None).cast("double"))
#     )
#     .persist(StorageLevel.MEMORY_AND_DISK)
# )

# df_done = (
#     df_item
#     .filter(F.col("goods_receipt_date").isNotNull())
#     .withColumn("actual_lt_days", F.datediff("goods_receipt_date", "po_creation_date").cast("double"))
#     .filter((F.col("actual_lt_days") >= F.lit(MIN_LT_DAYS)) & (F.col("actual_lt_days") <= F.lit(MAX_LT_DAYS)))
#     .withColumn("moy", F.month("po_creation_date").cast("int"))
#     .withColumn("month_index", (F.year("po_creation_date") * 12 + F.month("po_creation_date")).cast("int"))
#     .withColumn("has_req_date", (F.col("planned_deliv_time").isNotNull()).cast("int"))
#     .withColumn(
#         "delay_days_signed",
#         F.when(F.col("has_req_date") == 1, (F.col("actual_lt_days") - F.col("planned_deliv_time")).cast("double"))
#          .otherwise(F.lit(None).cast("double"))
#     )
#     .withColumn(
#         "lateness_days",
#         F.when(F.col("delay_days_signed").isNotNull(), F.greatest(F.col("delay_days_signed"), F.lit(0.0)))
#          .otherwise(F.lit(None).cast("double"))
#     )
#     .withColumn(
#         "is_delay",
#         F.when(F.col("has_req_date") == 0, F.lit(None).cast("int"))
#          .when(F.col("delay_days_signed") > 0, F.lit(1))
#          .otherwise(F.lit(0))
#     )
#     .persist(StorageLevel.MEMORY_AND_DISK)
# )

# n_item = df_item.count()
# n_done = df_done.count()
# log_step("Counts", extra=f"df_item={n_item} df_done={n_done}")

# # =======================
# # 2) OUTLIER FLAG (MAD) on df_done using actual_lt_days
# # =======================
# def median_by(df: DataFrame, group_cols: List[str], value_col: str, n_col: str, med_col: str) -> DataFrame:
#     return (
#         df.groupBy(*group_cols)
#           .agg(
#               F.count("*").alias(n_col),
#               F.expr(f"percentile_approx({value_col}, 0.5, {ACC})").cast("double").alias(med_col),
#           )
#     )

# med_key = median_by(df_done, keys, "actual_lt_days", "n_key", "med_key")
# med_vm  = median_by(df_done, ["vendor_id","material_code"], "actual_lt_days", "n_vm", "med_vm")
# med_v   = median_by(df_done, ["vendor_id"], "actual_lt_days", "n_v", "med_v")

# mad_key = (
#     df_done.join(med_key.select(*keys, "med_key"), keys, "left")
#            .withColumn("abs_dev", F.abs(F.col("actual_lt_days") - F.col("med_key")))
#            .groupBy(*keys)
#            .agg(F.expr(f"percentile_approx(abs_dev, 0.5, {ACC})").cast("double").alias("mad_key"))
# )

# mad_vm = (
#     df_done.join(med_vm.select("vendor_id","material_code","med_vm"), ["vendor_id","material_code"], "left")
#            .withColumn("abs_dev", F.abs(F.col("actual_lt_days") - F.col("med_vm")))
#            .groupBy("vendor_id","material_code")
#            .agg(F.expr(f"percentile_approx(abs_dev, 0.5, {ACC})").cast("double").alias("mad_vm"))
# )

# mad_v = (
#     df_done.join(med_v.select("vendor_id","med_v"), ["vendor_id"], "left")
#            .withColumn("abs_dev", F.abs(F.col("actual_lt_days") - F.col("med_v")))
#            .groupBy("vendor_id")
#            .agg(F.expr(f"percentile_approx(abs_dev, 0.5, {ACC})").cast("double").alias("mad_v"))
# )

# df_done_stats = (
#     df_done
#     .join(med_key.select(*keys, "n_key", "med_key"), keys, "left").join(mad_key, keys, "left")
#     .join(med_vm.select("vendor_id","material_code","n_vm","med_vm"), ["vendor_id","material_code"], "left").join(mad_vm, ["vendor_id","material_code"], "left")
#     .join(med_v.select("vendor_id","n_v","med_v"), ["vendor_id"], "left").join(mad_v, ["vendor_id"], "left")
#     .withColumn(
#         "outlier_scope",
#         F.when((F.col("n_key") >= F.lit(MIN_N_FOR_MAD_KEY)) & (F.col("mad_key") > F.lit(0)), F.lit("KEY"))
#          .when((F.col("n_vm") >= F.lit(MIN_N_FOR_MAD_VENDOR_MAT)) & (F.col("mad_vm") > F.lit(0)), F.lit("VENDOR_MATERIAL"))
#          .when((F.col("n_v")  >= F.lit(MIN_N_FOR_MAD_VENDOR)) & (F.col("mad_v")  > F.lit(0)), F.lit("VENDOR"))
#          .otherwise(F.lit("INSUFFICIENT"))
#     )
#     .withColumn(
#         "out_med",
#         F.when(F.col("outlier_scope")=="KEY", F.col("med_key"))
#          .when(F.col("outlier_scope")=="VENDOR_MATERIAL", F.col("med_vm"))
#          .when(F.col("outlier_scope")=="VENDOR", F.col("med_v"))
#          .otherwise(F.lit(None).cast("double"))
#     )
#     .withColumn(
#         "out_mad",
#         F.when(F.col("outlier_scope")=="KEY", F.col("mad_key"))
#          .when(F.col("outlier_scope")=="VENDOR_MATERIAL", F.col("mad_vm"))
#          .when(F.col("outlier_scope")=="VENDOR", F.col("mad_v"))
#          .otherwise(F.lit(None).cast("double"))
#     )
#     .withColumn(
#         "outlier_z",
#         F.when(
#             F.col("out_mad").isNotNull() & (F.col("out_mad") > 0),
#             (F.lit(0.6745) * (F.col("actual_lt_days") - F.col("out_med")) / F.col("out_mad"))
#         ).otherwise(F.lit(None).cast("double"))
#     )
#     .withColumn(
#         "is_outlier",
#         F.when(F.col("outlier_z").isNotNull() & (F.abs(F.col("outlier_z")) > F.lit(OUTLIER_Z)), F.lit(1)).otherwise(F.lit(0))
#     )
#     .withColumn(
#         "outlier_method",
#         F.when(F.col("outlier_scope") == "INSUFFICIENT", F.lit("NO_OUTLIER_TEST"))
#          .otherwise(F.concat(F.lit("MAD_"), F.col("outlier_scope")))
#     )
#     .persist(StorageLevel.MEMORY_AND_DISK)
# )

# n_out = df_done_stats.filter("is_outlier=1").count()
# log_step("Outliers", extra=f"rows={df_done_stats.count()} outliers={n_out}")

# # remove outliers for training/feature building
# base_clean = df_done_stats.filter(F.col("is_outlier") == F.lit(0)).persist(StorageLevel.MEMORY_AND_DISK)
# log_step("Base clean", extra=f"rows={base_clean.count()}")















# from pyspark.sql import functions as F

# MIN_OBS_PVM_MOY = 10
# keys = ["plant_code","vendor_id","material_code"]

# pvm_moy_n = (
#     base_clean
#     .groupBy(*keys, "moy")
#     .agg(F.count("*").alias("n_pvm_moy"))
# )

# bucketed = (
#     pvm_moy_n
#     .withColumn(
#         "n_bucket",
#         F.when(F.col("n_pvm_moy")==0, "0")
#          .when(F.col("n_pvm_moy")<4, "1-3")
#          .when(F.col("n_pvm_moy")<10, "4-9")
#          .when(F.col("n_pvm_moy")<20, "10-19")
#          .when(F.col("n_pvm_moy")<50, "20-49")
#          .otherwise("50+")
#     )
# )

# dist = (
#     bucketed.groupBy("n_bucket")
#     .agg(F.count("*").alias("lane_months"))
#     .withColumn("pct_lane_months", F.col("lane_months") / F.lit(bucketed.count()) * 100.0)
# )

# # Optional: enforce a nice order
# order_map = F.create_map(
#     [F.lit(x) for x in [
#         "0", 0,
#         "1-3", 1,
#         "4-9", 2,
#         "10-19", 3,
#         "20-49", 4,
#         "50+", 5
#     ]]
# )

# dist_nice = dist.withColumn("bucket_order", order_map[F.col("n_bucket")]).orderBy("bucket_order").drop("bucket_order")
# display(dist_nice)

















# # # =======================
# # # 3) SPLIT train vs holdout (for leakage-safe eval)
# # # =======================
# # train_df, holdout_df = split_time(base_clean, HOLDOUT_DAYS)
# # train_df = train_df.persist(StorageLevel.MEMORY_AND_DISK)
# # holdout_df = holdout_df.persist(StorageLevel.MEMORY_AND_DISK)

# # n_train = train_df.count()
# # n_hold = holdout_df.count()
# # log_step("Split", extra=f"train={n_train} holdout={n_hold}")
# # if n_train < MIN_TRAIN_ROWS:
# #     raise ValueError(f"Not enough train data: train={n_train}")

# # # =======================
# # # 4) FEATURE TABLES BUILT FROM TRAIN ONLY (leakage-safe)
# # # =======================
# # # Global priors
# # global_pri = train_df.agg(
# #     F.expr(f"percentile_approx(actual_lt_days, 0.5, {ACC})").cast("double").alias("global_p50"),
# #     F.expr(f"percentile_approx(actual_lt_days, 0.8, {ACC})").cast("double").alias("global_p80"),
# # ).first()
# # GLOBAL_P50 = float(global_pri["global_p50"]) if global_pri["global_p50"] is not None else 30.0
# # log_step("Global priors", extra=str({"global_p50": GLOBAL_P50, "global_p80": float(global_pri["global_p80"])}))

# # # Baselines
# # pvm_moy = (
# #     train_df.groupBy(*keys, "moy")
# #     .agg(
# #         F.count("*").alias("n_pvm_moy"),
# #         F.expr(f"percentile_approx(actual_lt_days, 0.5, {ACC})").cast("double").alias("p50_pvm_moy"),
# #     )
# # ).persist(StorageLevel.MEMORY_AND_DISK)

# # pvm_p50 = (
# #     train_df.groupBy(*keys)
# #     .agg(
# #         F.count("*").alias("n_pvm"),
# #         F.expr(f"percentile_approx(actual_lt_days, 0.5, {ACC})").cast("double").alias("p50_pvm")
# #     )
# # ).persist(StorageLevel.MEMORY_AND_DISK)

# # # UNKNOWN-material fallbacks: PV and V
# # pv_p50 = (
# #     train_df.groupBy(*pv_keys)
# #     .agg(
# #         F.count("*").alias("n_pv"),
# #         F.expr(f"percentile_approx(actual_lt_days, 0.5, {ACC})").cast("double").alias("p50_pv")
# #     )
# # ).persist(StorageLevel.MEMORY_AND_DISK)

# # v_p50 = (
# #     train_df.groupBy("vendor_id")
# #     .agg(
# #         F.count("*").alias("n_v"),
# #         F.expr(f"percentile_approx(actual_lt_days, 0.5, {ACC})").cast("double").alias("p50_v")
# #     )
# # ).persist(StorageLevel.MEMORY_AND_DISK)

# # # PV reliability (from TRAIN only)
# # pv_rel = (
# #     train_df
# #     .withColumn("is_delay_01", F.when(F.col("has_req_date")==1, F.col("is_delay").cast("double")).otherwise(F.lit(None).cast("double")))
# #     .groupBy(*pv_keys)
# #     .agg(
# #         F.count("*").alias("pv_completed_orders_rows"),
# #         (F.sum("is_outlier") / F.count("*")).cast("double").alias("outlier_rate"),  # train_df already has is_outlier=0, but keep schema
# #         F.avg("is_delay_01").alias("delay_rate_with_req"),
# #         F.expr("percentile_approx(CASE WHEN has_req_date=1 THEN lateness_days ELSE NULL END, 0.5)").cast("double").alias("median_lateness_days"),
# #         F.stddev_samp("actual_lt_days").alias("std_actual"),
# #     )
# # ).persist(StorageLevel.MEMORY_AND_DISK)

# # # PVM gap features (planned vs actual) using TRAIN:
# # # planned derived from df_item filtered to TRAIN time window to avoid leakage
# # holdout_start = F.date_sub(RUN_DATE, HOLDOUT_DAYS)
# # df_item_train = df_item.filter(F.col("po_creation_date") < holdout_start)

# # pvm_gap = (
# #     df_item_train.groupBy(*keys)
# #     .agg(
# #         F.expr(f"percentile_approx(planned_deliv_time, 0.5, {ACC})").cast("double").alias("planned_p50_days"),
# #         F.avg(F.col("planned_deliv_time").isNotNull().cast("double")).alias("req_date_coverage_rate")
# #     )
# #     .join(
# #         train_df.groupBy(*keys).agg(
# #             F.expr(f"percentile_approx(actual_lt_days, 0.5, {ACC})").cast("double").alias("actual_p50_days")
# #         ),
# #         keys,
# #         "left"
# #     )
# #     .withColumn("delta_planned_actual", (F.col("actual_p50_days") - F.col("planned_p50_days")).cast("double"))
# #     .drop("actual_p50_days")
# #     .persist(StorageLevel.MEMORY_AND_DISK)
# # )

# # # KPI tables (optional but used in scenario output)
# # overall_kpis = (
# #     train_df.groupBy(*keys)
# #     .agg(
# #         F.avg("actual_lt_days").alias("avg_actual_lead_time_overall"),
# #         F.stddev_samp("actual_lt_days").alias("std_deviation_overall"),
# #         F.count("*").alias("orders_overall"),
# #     )
# # ).persist(StorageLevel.MEMORY_AND_DISK)

# # by_moy_kpis = (
# #     train_df.groupBy(*keys, "moy")
# #     .agg(
# #         F.avg("actual_lt_days").alias("avg_actual_lead_time_moy"),
# #         F.stddev_samp("actual_lt_days").alias("std_deviation_moy"),
# #         F.count("*").alias("orders_moy"),
# #     )
# #     .withColumn(
# #         "std_deviation_moy",
# #         F.when(F.col("orders_moy") >= F.lit(MIN_OBS_CURRENT_MOY), F.col("std_deviation_moy"))
# #          .otherwise(F.lit(None).cast("double"))
# #     )
# # ).persist(StorageLevel.MEMORY_AND_DISK)

# # log_step("Feature tables", extra="pvm_moy/pvm_p50/pv_p50/v_p50/pv_rel/pvm_gap ready")

# # # =======================
# # # 5) TRAIN RESIDUAL MODEL (ONLY on ML-eligible PVM+MOY + non-UNKNOWN material)
# # # =======================
# # def train_residual_model(train_rows: DataFrame, model_type: str) -> Optional[Pipeline]:
# #     unk = is_unknown_material_expr("material_code")

# #     df = (
# #         train_rows
# #         .join(F.broadcast(pvm_moy), keys + ["moy"], "left")
# #         .join(F.broadcast(pvm_p50), keys, "left")
# #         .join(F.broadcast(pv_rel), pv_keys, "left")
# #         .join(F.broadcast(pvm_gap), keys, "left")
# #         .withColumn("baseline_p50", F.col("p50_pvm_moy").cast("double"))
# #         .withColumn("ml_eligible", (F.col("n_pvm_moy") >= F.lit(MIN_OBS_PVM_MOY)) & F.col("p50_pvm_moy").isNotNull() & (~unk))
# #         # extra overall context
# #         .withColumn("p50_pvm", F.col("p50_pvm").cast("double"))
# #         .withColumn("n_pvm", F.col("n_pvm").cast("double"))
# #         .withColumn("month_effect_baseline", (F.col("p50_pvm_moy") - F.col("p50_pvm")).cast("double"))
# #         .withColumn(
# #             "moy_share",
# #             (F.col("n_pvm_moy").cast("double") / F.when(F.col("n_pvm") > 0, F.col("n_pvm")).otherwise(F.lit(None))).cast("double")
# #         )
# #         .filter(F.col("ml_eligible") == F.lit(True))
# #         .withColumn("y_resid", (F.col("actual_lt_days") - F.col("baseline_p50")).cast("double"))
# #         .filter(F.col("y_resid").isNotNull())
# #     )

# #     n_elig = df.count()
# #     if n_elig < 200:
# #         log_step("Residual ML", extra=f"Not enough ML-eligible rows ({n_elig}), skipping ML")
# #         return None

# #     df = add_seasonality(df).withColumn("month_index", F.col("month_index").cast("double"))

# #     feat_cols = [
# #         # baseline + overall context
# #         "baseline_p50",
# #         "p50_pvm","n_pvm","month_effect_baseline","moy_share",
# #         # seasonality + trend
# #         "moy_sin","moy_cos","month_index",
# #         # reliability
# #         "outlier_rate","delay_rate_with_req","median_lateness_days","std_actual",
# #         # planned gap
# #         "planned_p50_days","delta_planned_actual","req_date_coverage_rate",
# #     ]

# #     for c in feat_cols:
# #         df = df.withColumn(c, to_finite(F.col(c), 0.0))

# #     assembler = VectorAssembler(inputCols=feat_cols, outputCol="features", handleInvalid="skip")

# #     if model_type == "lr":
# #         reg = LinearRegression(labelCol="y_resid", featuresCol="features", maxIter=60)
# #     elif model_type == "gbt":
# #         reg = GBTRegressor(
# #             labelCol="y_resid",
# #             featuresCol="features",
# #             maxDepth=6,
# #             maxIter=60,
# #             stepSize=0.075,
# #             subsamplingRate=0.8,
# #             minInstancesPerNode=50,
# #             maxBins=32,
# #             seed=SEED,
# #         )
# #     else:
# #         raise ValueError("RESIDUAL_MODEL must be 'lr' or 'gbt'")

# #     return Pipeline(stages=[assembler, reg]).fit(df)

# # model = None
# # if USE_RESIDUAL_ML:
# #     model = train_residual_model(train_df, RESIDUAL_MODEL)
# #     log_step("Residual ML", extra=("trained" if model is not None else "skipped"))

# # # =======================
# # # 6) SCORING FUNCTION (3-bucket + UNKNOWN fallback + ML only when allowed)
# # # =======================
# # def enrich_for_scoring(df_any: DataFrame) -> DataFrame:
# #     return (
# #         df_any
# #         .join(F.broadcast(pvm_moy), keys + ["moy"], "left")
# #         .join(F.broadcast(pvm_p50), keys, "left")
# #         .join(F.broadcast(pv_p50), pv_keys, "left")
# #         .join(F.broadcast(v_p50), ["vendor_id"], "left")
# #         .join(F.broadcast(pv_rel), pv_keys, "left")
# #         .join(F.broadcast(pvm_gap), keys, "left")
# #     )

# # def score_rows_3bucket(df_any: DataFrame, use_ml: bool) -> DataFrame:
# #     df = enrich_for_scoring(df_any)

# #     unk = is_unknown_material_expr("material_code")
# #     has_pvm_moy = F.col("p50_pvm_moy").isNotNull()
# #     pvm_moy_sufficient = has_pvm_moy & (F.col("n_pvm_moy") >= F.lit(MIN_OBS_PVM_MOY)) & (~unk)
# #     pvm_moy_insufficient = has_pvm_moy & (F.col("n_pvm_moy") < F.lit(MIN_OBS_PVM_MOY)) & (~unk)

# #     # baseline ladder for non-UNKNOWN
# #     no_ml_days_nonunk = F.when(pvm_moy_insufficient, F.col("p50_pvm_moy")).otherwise(F.col("p50_pvm"))
# #     no_ml_src_nonunk  = F.when(pvm_moy_insufficient, F.lit("NO_ML__PVM_MOY_Median")).otherwise(F.lit("NO_ML__PVM_Median"))

# #     # baseline ladder for UNKNOWN -> PV -> V -> global
# #     no_ml_days_unk = F.coalesce(F.col("p50_pv"), F.col("p50_v"), F.lit(GLOBAL_P50))
# #     no_ml_src_unk  = F.lit("NO_ML__UNKNOWN_MATERIAL__PV_V_GLOBAL")

# #     baseline_days = F.when(unk, no_ml_days_unk).otherwise(no_ml_days_nonunk)
# #     baseline_src  = (
# #         F.when(pvm_moy_sufficient, F.lit("ML_FROM_PVM_MOY"))
# #          .when(unk, no_ml_src_unk)
# #          .otherwise(no_ml_src_nonunk)
# #     )

# #     df = (
# #         df.withColumn("baseline_days", clamp_days(baseline_days.cast("double")))
# #           .withColumn("baseline_src", baseline_src)
# #     )

# #     # If ML off or model missing: just baseline
# #     if (not use_ml) or (model is None):
# #         return (
# #             df.withColumn("pred_days", F.col("baseline_days"))
# #               .withColumn("pred_src", F.col("baseline_src"))
# #               .withColumn("pred_resid", F.lit(None).cast("double"))
# #         )

# #     # Prepare features for model.transform on all rows, but apply ML only on pvm_moy_sufficient rows
# #     df_ml = add_seasonality(df).withColumn("month_index", F.col("month_index").cast("double"))

# #     df_ml = (
# #         df_ml
# #         .withColumn("baseline_p50", to_finite(F.col("p50_pvm_moy").cast("double"), 0.0))
# #         .withColumn("p50_pvm", to_finite(F.col("p50_pvm").cast("double"), 0.0))
# #         .withColumn("n_pvm", to_finite(F.col("n_pvm").cast("double"), 0.0))
# #         .withColumn("month_effect_baseline", to_finite((F.col("p50_pvm_moy") - F.col("p50_pvm")).cast("double"), 0.0))
# #         .withColumn(
# #             "moy_share",
# #             to_finite((F.col("n_pvm_moy").cast("double") / F.when(F.col("n_pvm") > 0, F.col("n_pvm")).otherwise(F.lit(None))).cast("double"), 0.0)
# #         )
# #     )

# #     for c in ["moy_sin","moy_cos","month_index",
# #               "outlier_rate","delay_rate_with_req","median_lateness_days","std_actual",
# #               "planned_p50_days","delta_planned_actual","req_date_coverage_rate",
# #               "baseline_p50","p50_pvm","n_pvm","month_effect_baseline","moy_share"]:
# #         df_ml = df_ml.withColumn(c, to_finite(F.col(c), 0.0))

# #     pred = model.transform(df_ml)
# #     resid = clamp_resid(F.col("prediction").cast("double"))

# #     ml_pred_days = clamp_days((F.col("baseline_p50") + resid).cast("double"))

# #     final_days = F.when(pvm_moy_sufficient, ml_pred_days).otherwise(F.col("baseline_days"))
# #     final_src  = F.when(pvm_moy_sufficient, F.lit("ML_FROM_PVM_MOY")).otherwise(F.col("baseline_src"))
# #     final_res  = F.when(pvm_moy_sufficient, resid).otherwise(F.lit(None).cast("double"))

# #     return (
# #         pred.withColumn("pred_days", final_days)
# #             .withColumn("pred_src", final_src)
# #             .withColumn("pred_resid", final_res)
# #     )

# # # =======================
# # # 7) HOLDOUT EVAL (leakage-safe) + debug rows actual vs pred
# # # =======================
# # hold_base = score_rows_3bucket(holdout_df, use_ml=False).withColumn("model", F.lit("BASELINE"))
# # hold_hybr = score_rows_3bucket(holdout_df, use_ml=True ).withColumn("model", F.lit("HYBRID_ML"))

# # hold_rows = (
# #     hold_base
# #     .select("po_number","po_creation_date",*keys,"moy","actual_lt_days","pred_days","pred_src","pred_resid","model")
# #     .unionByName(
# #         hold_hybr.select("po_number","po_creation_date",*keys,"moy","actual_lt_days","pred_days","pred_src","pred_resid","model")
# #     )
# #     .withColumn("abs_err", F.abs(F.col("actual_lt_days") - F.col("pred_days")))
# #     .withColumn("signed_err", (F.col("pred_days") - F.col("actual_lt_days")).cast("double"))
# #     .persist(StorageLevel.MEMORY_AND_DISK)
# # )
# # _ = hold_rows.count()

# # # Aggregate eval: by baseline_level (pred_src) and model
# # eval_by_level = (
# #     hold_rows.groupBy("pred_src","model")
# #     .agg(
# #         F.count("*").alias("n"),
# #         mae("actual_lt_days", "pred_days"),
# #         medae("actual_lt_days", "pred_days"),
# #         rmse("actual_lt_days", "pred_days"),
# #     )
# #     .withColumnRenamed("pred_src","baseline_level")
# #     .orderBy("model","baseline_level")
# # )
# # display(eval_by_level)

# # # Extra eval for planner-thinking: directionality + tail risk
# # eval_planner = (
# #     hold_rows.groupBy("pred_src","model")
# #     .agg(
# #         F.count("*").alias("n"),
# #         mae("actual_lt_days","pred_days"),
# #         medae("actual_lt_days","pred_days"),
# #         F.expr(f"percentile_approx(abs_err, 0.90, {ACC})").cast("double").alias("p90_abs_err"),
# #         F.avg("signed_err").cast("double").alias("mean_signed_err"),
# #     )
# #     .orderBy("model","pred_src")
# # )
# # display(eval_planner)

# # # Debug: worst errors (HYBRID_ML)
# # display(
# #     hold_rows.filter(F.col("model")=="HYBRID_ML")
# #              .orderBy(F.desc("abs_err"))
# #              .select("po_number","po_creation_date",*keys,"moy","actual_lt_days","pred_days","pred_src","pred_resid","abs_err","signed_err")
# #              .limit(50)
# # )

# # # =======================
# # # 8) SCENARIOS (current date, +1 month, +2 months) and SCORE
# # # =======================
# # df_items = train_df.select(*keys).distinct().persist(StorageLevel.MEMORY_AND_DISK)
# # _ = df_items.count()

# # run = RUN_DATE.cast("date")
# # m1  = F.add_months(F.date_trunc("month", run).cast("date"), 1)
# # m2  = F.add_months(F.date_trunc("month", run).cast("date"), 2)

# # scenarios = (
# #     df_items
# #     .withColumn("scenario_k", F.explode(F.array(F.lit(0), F.lit(1), F.lit(2))))
# #     .withColumn(
# #         "po_creation_date",
# #         F.when(F.col("scenario_k")==0, run)
# #          .when(F.col("scenario_k")==1, m1)
# #          .otherwise(m2)
# #     )
# #     .withColumn("moy", F.month("po_creation_date").cast("int"))
# #     .withColumn("month_index", (F.year("po_creation_date") * 12 + F.month("po_creation_date")).cast("int"))
# #     .persist(StorageLevel.MEMORY_AND_DISK)
# # )
# # _ = scenarios.count()

# # # Add KPI tables to scenarios (optional but you asked earlier)
# # sc = (
# #     scenarios
# #     .join(F.broadcast(by_moy_kpis), keys + ["moy"], "left")
# #     .join(F.broadcast(overall_kpis), keys, "left")
# # )

# # sc_scored = (
# #     score_rows_3bucket(sc, use_ml=True)
# #     .withColumn("eta_pred_date", F.date_add(F.col("po_creation_date"), F.col("pred_days").cast("int")))
# #     .withColumnRenamed("pred_days","lt_pred_days")
# #     .withColumnRenamed("pred_src","lt_pred_source")
# #     .persist(StorageLevel.MEMORY_AND_DISK)
# # )
# # _ = sc_scored.count()

# # # =======================
# # # 9) WIDE OUTPUT (per scenario)
# # # =======================
# # def wide_max(colname: str, k: int, alias: str):
# #     return F.max(F.when(F.col("scenario_k")==k, F.col(colname))).alias(alias)

# # final_eta = (
# #     sc_scored.groupBy(*keys)
# #     .agg(
# #         wide_max("eta_pred_date", 0, "eta_current_month"),
# #         wide_max("eta_pred_date", 1, "eta_month_plus_1"),
# #         wide_max("eta_pred_date", 2, "eta_month_plus_2"),

# #         wide_max("lt_pred_days", 0, "lt_days_current_month"),
# #         wide_max("lt_pred_days", 1, "lt_days_month_plus_1"),
# #         wide_max("lt_pred_days", 2, "lt_days_month_plus_2"),

# #         wide_max("lt_pred_source", 0, "lt_source_current_month"),
# #         wide_max("lt_pred_source", 1, "lt_source_month_plus_1"),
# #         wide_max("lt_pred_source", 2, "lt_source_month_plus_2"),

# #         # overall KPIs (train-based)
# #         F.max("avg_actual_lead_time_overall").alias("avg_actual_lead_time_overall"),
# #         F.max("std_deviation_overall").alias("std_deviation_overall"),
# #         F.max("orders_overall").alias("orders_overall"),

# #         # scenario-moy KPIs (train-based)
# #         wide_max("avg_actual_lead_time_moy", 0, "avg_actual_lead_time_PVM_current_month"),
# #         wide_max("avg_actual_lead_time_moy", 1, "avg_actual_lead_time_PVM_month_plus_1"),
# #         wide_max("avg_actual_lead_time_moy", 2, "avg_actual_lead_time_PVM_month_plus_2"),

# #         wide_max("std_deviation_moy", 0, "std_deviation_lead_time_PVM_current_month"),
# #         wide_max("std_deviation_moy", 1, "std_deviation_lead_time_PVM_month_plus_1"),
# #         wide_max("std_deviation_moy", 2, "std_deviation_lead_time_PVM_month_plus_2"),

# #         wide_max("orders_moy", 0, "orders_PVM_current_month"),
# #         wide_max("orders_moy", 1, "orders_PVM_month_plus_1"),
# #         wide_max("orders_moy", 2, "orders_PVM_month_plus_2"),
# #     )
# #     .persist(StorageLevel.MEMORY_AND_DISK)
# # )
# # _ = final_eta.count()

# # # =======================
# # # 10) FINAL TABLE (optionally keep reliability/gap tables once)
# # # =======================
# # final_clean = (
# #     final_eta
# #     .join(pv_rel, pv_keys, "left")
# #     .join(pvm_gap, keys, "left")
# #     .join(pv_p50, pv_keys, "left")
# #     .join(v_p50, ["vendor_id"], "left")
# #     .withColumn("variant_name", F.lit("NO_OUTLIERS_3BUCKET_MVP__UNKNOWN_FALLBACK__LEAKAGE_SAFE_EVAL"))
# #     .persist(StorageLevel.MEMORY_AND_DISK)
# # )

# # _ = final_clean.count()
# # display(final_clean)


# COMMAND ----------

# MAGIC %md
# MAGIC ### Save

# COMMAND ----------

# final_clean.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{GOLD}.lead_time_forecasts")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Statistical Approach with ML

# COMMAND ----------

# ============================================================
# SINGLE CELL — PLANNER-READY LEAD TIME SCORER (REQ-DATE FREE PREDICTION)
# - Prediction uses ONLY: actual lead time history + MOY seasonality + hierarchy (PVM/PV/Global)
# - Reliability KPIs (delay_rate, median_lateness, coverage) computed from req-date history, NOT required for prediction
# - Produces: ETA for (today, same-day +1/+2/+3 months) + p50/p80 + source + confidence
# - Keeps existing exact-MOY fields and adds parallel 3M seasonal-window stats
# - Adds supplier classification based on:
#     1) Std deviation of lead time
#     2) CV = std / p50
# ============================================================

import time
from typing import List, Tuple

import pyspark.sql.functions as F
from pyspark.sql import DataFrame
from pyspark.storagelevel import StorageLevel

# =======================
# CONFIG
# =======================
RUN_DATE = F.current_date()
LOOKBACK_YEARS = 3
HOLDOUT_DAYS = 90

ACC = 50
MIN_LT_DAYS = 1
MAX_LT_DAYS = 365
MIN_TRAIN_ROWS = 1000

# Outliers (MAD z-score)
OUTLIER_Z = 3.5

# =======================
# MAD severity thresholds
# =======================
MAD_NORMAL_MAX = 2.0
MAD_MILD_MAX = 3.5
MAD_STRONG_MAX = 5.0


MIN_N_FOR_MAD_KEY = 10
MIN_N_FOR_MAD_PV  = 20
MIN_N_FOR_MAD_V   = 50

# Candidate minimums (lowered for better coverage; shrink handles small n)
MIN_N_PVM_MOY = 4
MIN_N_PV_MOY  = 4

# Shrink / sanity / seatbelt
TAU = 80.0
SANITY_SIGMA = 2.0
SEATBELT_SIGMA = 3.0
STD_FALLBACK = 15.0

# Dual-anchor sanity
ANCHOR_DIFF_DAYS = 30.0
ANCHOR_DIFF_SIGMA = 4.0

# Supplier classification thresholds
# Std deviation based classes (days)
STD_CLASS_A_MAX = 10.0   # Very Reliable
STD_CLASS_B_MAX = 25.0   # Reliable
STD_CLASS_C_MAX = 45.0   # Unstable
# > 45 => Highly Unreliable

# Optional minimum observations to trust supplier classification
MIN_N_SUPPLIER_CLASS = 5

# Perf
spark.conf.set("spark.sql.shuffle.partitions", "64")
spark.conf.set("spark.sql.adaptive.enabled", "true")
spark.conf.set("spark.sql.autoBroadcastJoinThreshold", str(104857600))
spark.conf.set("spark.sql.broadcastTimeout", str(1200))

keys    = ["plant_code", "vendor_id", "material_code"]
pv_keys = ["plant_code", "vendor_id"]

INVALID_KEY_STR = "-1"
lookback_start = F.add_months(RUN_DATE, -12 * LOOKBACK_YEARS)

# =======================
# HELPERS
# =======================
def log_step(msg: str, extra: str = ""):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}" + (f" | {extra}" if extra else ""))

def clamp_days(c):
    return F.when(c.isNull(), None).otherwise(
        F.greatest(F.lit(float(MIN_LT_DAYS)), F.least(c, F.lit(float(MAX_LT_DAYS))))
    )

def is_unknown_material_expr(colname="material_code"):
    c = F.col(colname)
    return (
        c.isNull() |
        (F.length(F.trim(c)) == 0) |
        (F.upper(F.trim(c)).isin("UNKNOWN", "UNK", "N/A", "NA", "NULL"))
    )

def split_time(df: DataFrame, holdout_days: int) -> Tuple[DataFrame, DataFrame]:
    holdout_start = F.date_sub(RUN_DATE, holdout_days)
    return (
        df.filter(F.col("po_creation_date") < holdout_start),
        df.filter(F.col("po_creation_date") >= holdout_start),
    )

def mae(col_y, col_yhat):
    return F.avg(F.abs(F.col(col_y) - F.col(col_yhat))).alias("mae")

def medae(col_y, col_yhat):
    return F.expr(f"percentile_approx(abs({col_y} - {col_yhat}), 0.5)").cast("double").alias("medae")

def rmse(col_y, col_yhat):
    return F.sqrt(F.avg(F.pow(F.col(col_y) - F.col(col_yhat), 2))).alias("rmse")

def median_by(df: DataFrame, group_cols: List[str], value_col: str, n_col: str, med_col: str) -> DataFrame:
    return (
        df.groupBy(*group_cols)
          .agg(
              F.count("*").alias(n_col),
              F.expr(f"percentile_approx({value_col}, 0.5, {ACC})").cast("double").alias(med_col),
          )
    )

def stats_table(df: DataFrame, group_cols: List[str], suffix: str) -> DataFrame:
    return (
        df.groupBy(*group_cols)
          .agg(
              F.count("*").alias(f"n_{suffix}"),
              F.expr(f"percentile_approx(actual_lt_days, 0.5, {ACC})").cast("double").alias(f"p50_{suffix}"),
              F.expr(f"percentile_approx(actual_lt_days, 0.8, {ACC})").cast("double").alias(f"p80_{suffix}"),
              F.stddev_samp("actual_lt_days").cast("double").alias(f"std_{suffix}"),
          )
    )

def shrink_alpha(n_col, tau: float) -> F.Column:
    n = F.coalesce(n_col.cast("double"), F.lit(0.0))
    return (n / (n + F.lit(float(tau)))).cast("double")

def sane_range(p50_col, n_col, min_n: int, anchor_col, std_col) -> F.Column:
    ok_n = n_col.isNotNull() & (n_col >= F.lit(int(min_n)))
    std  = F.coalesce(std_col.cast("double"), F.lit(float(STD_FALLBACK)))
    lo = F.greatest(F.lit(float(MIN_LT_DAYS)), anchor_col - F.lit(float(SANITY_SIGMA)) * std)
    hi = F.least(F.lit(float(MAX_LT_DAYS)), anchor_col + F.lit(float(SANITY_SIGMA)) * std)
    ok_range = p50_col.isNotNull() & (p50_col >= lo) & (p50_col <= hi)
    return (ok_n & ok_range).cast("int")

def prev_month_expr(c: F.Column) -> F.Column:
    return F.when(c == 1, F.lit(12)).otherwise(c - 1)

def next_month_expr(c: F.Column) -> F.Column:
    return F.when(c == 12, F.lit(1)).otherwise(c + 1)

def classify_supplier_std(std_col: F.Column, n_col: F.Column = None) -> F.Column:
    """
    Classify supplier reliability based on std deviation of actual lead time.
    """
    base = (
        F.when(std_col.isNull(), F.lit("UNKNOWN"))
         .when(std_col < F.lit(STD_CLASS_A_MAX), F.lit("Class A: Very Reliable"))
         .when(std_col < F.lit(STD_CLASS_B_MAX), F.lit("Class B: Reliable"))
         .when(std_col < F.lit(STD_CLASS_C_MAX), F.lit("Class C: Unstable"))
         .otherwise(F.lit("Class D: Highly Unreliable"))
    )

    if n_col is not None:
        base = F.when(
            n_col.isNull() | (n_col < F.lit(MIN_N_SUPPLIER_CLASS)),
            F.lit("INSUFFICIENT_HISTORY")
        ).otherwise(base)

    return base

def classify_supplier_cv(cv_col: F.Column, n_col: F.Column = None) -> F.Column:
    """
    Classify supplier reliability based on coefficient of variation (CV = std / p50).
    """
    base = (
        F.when(cv_col.isNull(), F.lit("UNKNOWN"))
         .when(cv_col < F.lit(0.10), F.lit("Class A: Very Reliable"))
         .when(cv_col < F.lit(0.25), F.lit("Class B: Reliable"))
         .when(cv_col < F.lit(0.50), F.lit("Class C: Unstable"))
         .otherwise(F.lit("Class D: Highly Unreliable"))
    )

    if n_col is not None:
        base = F.when(
            n_col.isNull() | (n_col < F.lit(MIN_N_SUPPLIER_CLASS)),
            F.lit("INSUFFICIENT_HISTORY")
        ).otherwise(base)

    return base

def interpret_supplier_class(class_col: F.Column) -> F.Column:
    return (
        F.when(class_col == "Class A: Very Reliable", F.lit("Very stable lead time"))
         .when(class_col == "Class B: Reliable", F.lit("Acceptable variation"))
         .when(class_col == "Class C: Unstable", F.lit("Requires buffer increase"))
         .when(class_col == "Class D: Highly Unreliable", F.lit("Critical risk"))
         .when(class_col == "INSUFFICIENT_HISTORY", F.lit("Not enough supplier history"))
         .otherwise(F.lit("Unknown"))
    )

# =======================
# 1) Build df_item + df_done (3Y window, remove invalid keys)
# =======================
df_item = (
    df0
    .select(
        F.col("po_creation_date").cast("date").alias("po_creation_date"),
        F.col("plant_code").cast("string").alias("plant_code"),
        F.col("vendor_id").cast("string").alias("vendor_id"),
        F.col("material_code").cast("string").alias("material_code"),
        F.col("goods_receipt_date").cast("date").alias("goods_receipt_date"),
        F.col("req_delivery_date").cast("date").alias("req_delivery_date"),
        F.col("po_number").cast("string").alias("po_number"),
    )
    .filter(F.col("po_creation_date").isNotNull())
    .filter(F.col("po_creation_date") >= lookback_start)
    .filter(
        F.col("plant_code").isNotNull() & F.col("vendor_id").isNotNull() & F.col("material_code").isNotNull() &
        (F.col("plant_code") != F.lit(INVALID_KEY_STR)) &
        (F.col("vendor_id")  != F.lit(INVALID_KEY_STR)) &
        (F.col("material_code") != F.lit(INVALID_KEY_STR))
    )
    .withColumn(
        "planned_req_lt_days",
        F.when(
            F.col("req_delivery_date").isNotNull(),
            F.datediff("req_delivery_date", "po_creation_date").cast("double")
        ).otherwise(F.lit(None).cast("double"))
    )
    .withColumn("has_req_date", (F.col("planned_req_lt_days").isNotNull()).cast("int"))
    .persist(StorageLevel.MEMORY_AND_DISK)
)

df_done = (
    df_item
    .filter(F.col("goods_receipt_date").isNotNull())
    .withColumn("actual_lt_days", F.datediff("goods_receipt_date", "po_creation_date").cast("double"))
    .filter((F.col("actual_lt_days") >= F.lit(MIN_LT_DAYS)) & (F.col("actual_lt_days") <= F.lit(MAX_LT_DAYS)))
    .withColumn("moy", F.month("po_creation_date").cast("int"))
    .persist(StorageLevel.MEMORY_AND_DISK)
)

log_step("Counts", extra=f"df_item={df_item.count()} df_done={df_done.count()}")

# =======================
# 2) OUTLIER FLAG (MAD) — scope: KEY -> PV -> V
# =======================
med_key = median_by(df_done, keys, "actual_lt_days", "n_key", "med_key")
med_pv  = median_by(df_done, pv_keys, "actual_lt_days", "n_pv_med", "med_pv")
med_v   = median_by(df_done, ["vendor_id"], "actual_lt_days", "n_v_med", "med_v")

mad_key = (
    df_done.join(med_key.select(*keys, "med_key"), keys, "left")
           .withColumn("abs_dev", F.abs(F.col("actual_lt_days") - F.col("med_key")))
           .groupBy(*keys)
           .agg(F.expr(f"percentile_approx(abs_dev, 0.5, {ACC})").cast("double").alias("mad_key"))
)

mad_pv = (
    df_done.join(med_pv.select(*pv_keys, "med_pv"), pv_keys, "left")
           .withColumn("abs_dev", F.abs(F.col("actual_lt_days") - F.col("med_pv")))
           .groupBy(*pv_keys)
           .agg(F.expr(f"percentile_approx(abs_dev, 0.5, {ACC})").cast("double").alias("mad_pv"))
)

mad_v = (
    df_done.join(med_v.select("vendor_id", "med_v"), ["vendor_id"], "left")
           .withColumn("abs_dev", F.abs(F.col("actual_lt_days") - F.col("med_v")))
           .groupBy("vendor_id")
           .agg(F.expr(f"percentile_approx(abs_dev, 0.5, {ACC})").cast("double").alias("mad_v"))
)

df_done_stats = (
    df_done
    .join(med_key.select(*keys, "n_key", "med_key"), keys, "left").join(mad_key, keys, "left")
    .join(med_pv.select(*pv_keys, "n_pv_med", "med_pv"), pv_keys, "left").join(mad_pv, pv_keys, "left")
    .join(med_v.select("vendor_id", "n_v_med", "med_v"), ["vendor_id"], "left").join(mad_v, ["vendor_id"], "left")
    .withColumn(
        "outlier_scope",
        F.when((F.col("n_key") >= F.lit(MIN_N_FOR_MAD_KEY)) & (F.col("mad_key") > F.lit(0)), F.lit("KEY"))
         .when((F.col("n_pv_med") >= F.lit(MIN_N_FOR_MAD_PV)) & (F.col("mad_pv") > F.lit(0)), F.lit("PV"))
         .when((F.col("n_v_med")  >= F.lit(MIN_N_FOR_MAD_V))  & (F.col("mad_v")  > F.lit(0)), F.lit("V"))
         .otherwise(F.lit("INSUFFICIENT"))
    )
    .withColumn(
        "out_med",
        F.when(F.col("outlier_scope") == "KEY", F.col("med_key"))
         .when(F.col("outlier_scope") == "PV",  F.col("med_pv"))
         .when(F.col("outlier_scope") == "V",   F.col("med_v"))
         .otherwise(F.lit(None).cast("double"))
    )
    .withColumn(
        "out_mad",
        F.when(F.col("outlier_scope") == "KEY", F.col("mad_key"))
         .when(F.col("outlier_scope") == "PV",  F.col("mad_pv"))
         .when(F.col("outlier_scope") == "V",   F.col("mad_v"))
         .otherwise(F.lit(None).cast("double"))
    )
    .withColumn(
        "outlier_z",
        F.when(
            F.col("out_mad").isNotNull() & (F.col("out_mad") > 0),
            (F.lit(0.6745) * (F.col("actual_lt_days") - F.col("out_med")) / F.col("out_mad"))
        ).otherwise(F.lit(None).cast("double"))
    )

    .withColumn(
        "outlier_abs_z",
        F.abs(F.col("outlier_z"))
    )

    .withColumn(
        "outlier_severity",
        F.when(F.col("outlier_abs_z").isNull(), "UNKNOWN")
        .when(F.col("outlier_abs_z") < MAD_NORMAL_MAX, "NORMAL")
        .when(F.col("outlier_abs_z") < MAD_MILD_MAX, "MILD_OUTLIER")
        .when(F.col("outlier_abs_z") < MAD_STRONG_MAX, "STRONG_OUTLIER")
        .otherwise("EXTREME_OUTLIER")
    )

    .withColumn(
        "is_outlier",
        F.when(
            F.col("outlier_severity").isin("STRONG_OUTLIER","EXTREME_OUTLIER"),
            F.lit(1)
        ).otherwise(F.lit(0))
    )

    # .withColumn(
    #     "outlier_z",
    #     F.when(
    #         F.col("out_mad").isNotNull() & (F.col("out_mad") > 0),
    #         (F.lit(0.6745) * (F.col("actual_lt_days") - F.col("out_med")) / F.col("out_mad"))
    #     ).otherwise(F.lit(None).cast("double"))
    # )
    # .withColumn(
    #     "is_outlier",
    #     F.when(
    #         F.col("outlier_z").isNotNull() & (F.abs(F.col("outlier_z")) > F.lit(OUTLIER_Z)),
    #         F.lit(1)
    #     ).otherwise(F.lit(0))
    # )
    
    .persist(StorageLevel.MEMORY_AND_DISK)
)


# base_clean = df_done_stats.filter(F.col("is_outlier") == F.lit(0)).persist(StorageLevel.MEMORY_AND_DISK)
base_clean = (
    df_done_stats
    .filter(
        F.col("outlier_severity").isin(
            "NORMAL",
            "MILD_OUTLIER"
        )
    )
    .persist(StorageLevel.MEMORY_AND_DISK)
)
# log_step("Outliers", extra=f"clean_rows={base_clean.count()} outliers={df_done_stats.filter('is_outlier=1').count()}")
severity_counts = (
    df_done_stats
    .groupBy("outlier_severity")
    .count()
)

display(severity_counts)

log_step(
    "Outlier severity distribution",
    extra=f"clean_rows={base_clean.count()}"
)

# =======================
# 3) SPLIT train vs holdout (leakage-safe)
# =======================
train_df, holdout_df = split_time(base_clean, HOLDOUT_DAYS)
train_df = train_df.persist(StorageLevel.MEMORY_AND_DISK)
holdout_df = holdout_df.persist(StorageLevel.MEMORY_AND_DISK)

n_train = train_df.count()
n_hold  = holdout_df.count()
log_step("Split", extra=f"train={n_train} holdout={n_hold}")
if n_train < MIN_TRAIN_ROWS:
    raise ValueError(f"Not enough train data: train={n_train}")

# =======================
# 4) FEATURE TABLES FROM TRAIN ONLY
# =======================
global_row = train_df.agg(
    F.expr(f"percentile_approx(actual_lt_days, 0.5, {ACC})").cast("double").alias("global_p50"),
    F.expr(f"percentile_approx(actual_lt_days, 0.8, {ACC})").cast("double").alias("global_p80"),
    F.stddev_samp("actual_lt_days").cast("double").alias("global_std"),
).first()

GLOBAL_P50 = float(global_row["global_p50"]) if global_row["global_p50"] is not None else 30.0
GLOBAL_P80 = float(global_row["global_p80"]) if global_row["global_p80"] is not None else 45.0
GLOBAL_STD = float(global_row["global_std"]) if global_row["global_std"] is not None else 15.0

log_step("Global p50", extra=str(GLOBAL_P50))

# Global seasonality
global_moy = (
    train_df.groupBy("moy")
    .agg(
        F.count("*").alias("n_global_moy"),
        F.expr(f"percentile_approx(actual_lt_days, 0.5, {ACC})").cast("double").alias("p50_global_moy"),
        F.expr(f"percentile_approx(actual_lt_days, 0.8, {ACC})").cast("double").alias("p80_global_moy"),
        F.stddev_samp("actual_lt_days").cast("double").alias("std_global_moy"),
    )
).persist(StorageLevel.MEMORY_AND_DISK)

# Hierarchy stats
ft_pvm     = stats_table(train_df, keys, "pvm").persist(StorageLevel.MEMORY_AND_DISK)
ft_pvm_moy = stats_table(train_df, keys + ["moy"], "pvm_moy").persist(StorageLevel.MEMORY_AND_DISK)

ft_pv      = stats_table(train_df, pv_keys, "pv").persist(StorageLevel.MEMORY_AND_DISK)
ft_pv_moy  = stats_table(train_df, pv_keys + ["moy"], "pv_moy").persist(StorageLevel.MEMORY_AND_DISK)

# Vendor-only tables
ft_v       = stats_table(train_df, ["vendor_id"], "v").persist(StorageLevel.MEMORY_AND_DISK)

# Reliability KPIs from req-date history
holdout_start = F.date_sub(RUN_DATE, HOLDOUT_DAYS)
df_item_train = df_item.filter(F.col("po_creation_date") < holdout_start)

pv_rel = (
    df_item_train
    .filter(F.col("goods_receipt_date").isNotNull())
    .withColumn("actual_lt_days", F.datediff("goods_receipt_date", "po_creation_date").cast("double"))
    .withColumn(
        "delay_days_signed",
        F.when(F.col("has_req_date") == 1, (F.col("actual_lt_days") - F.col("planned_req_lt_days")).cast("double"))
         .otherwise(F.lit(None).cast("double"))
    )
    .withColumn(
        "lateness_days",
        F.when(F.col("delay_days_signed").isNotNull(), F.greatest(F.col("delay_days_signed"), F.lit(0.0)))
         .otherwise(F.lit(None).cast("double"))
    )
    .withColumn(
        "is_delay",
        F.when(F.col("has_req_date") == 0, F.lit(None).cast("int"))
         .when(F.col("delay_days_signed") > 0, F.lit(1))
         .otherwise(F.lit(0))
    )
    .groupBy(*pv_keys)
    .agg(
        F.count("*").alias("pv_completed_orders_rows"),
        F.avg(
            F.when(F.col("has_req_date") == 1, F.col("is_delay").cast("double"))
             .otherwise(F.lit(None).cast("double"))
        ).alias("delay_rate_with_req"),
        F.expr("percentile_approx(CASE WHEN has_req_date=1 THEN lateness_days ELSE NULL END, 0.5)").cast("double").alias("median_lateness_days"),
        F.avg(F.col("has_req_date").cast("double")).alias("req_date_coverage_rate_train"),
    )
).persist(StorageLevel.MEMORY_AND_DISK)

# Planner KPIs (existing exact MOY)
overall_kpis = (
    train_df.groupBy(*keys)
    .agg(
        F.avg("actual_lt_days").alias("avg_actual_lead_time_overall"),
        F.stddev_samp("actual_lt_days").alias("std_deviation_overall"),
        F.count("*").alias("orders_overall"),
    )
).persist(StorageLevel.MEMORY_AND_DISK)

by_moy_kpis = (
    train_df.groupBy(*keys, "moy")
    .agg(
        F.avg("actual_lt_days").alias("avg_actual_lead_time_moy"),
        F.stddev_samp("actual_lt_days").alias("std_deviation_moy"),
        F.count("*").alias("orders_moy"),
    )
).persist(StorageLevel.MEMORY_AND_DISK)

# 3M seasonal window expansion
train_df_3m = (
    train_df
    .withColumn(
        "target_moy",
        F.explode(
            F.array(
                prev_month_expr(F.col("moy")),
                F.col("moy"),
                next_month_expr(F.col("moy"))
            )
        )
    )
    .persist(StorageLevel.MEMORY_AND_DISK)
)

# Raw 3M seasonal stats
ft_pvm_moy_3m = (
    train_df_3m
    .groupBy(*keys, "target_moy")
    .agg(
        F.count("*").alias("n_pvm_moy_3m"),
        F.expr(f"percentile_approx(actual_lt_days, 0.5, {ACC})").cast("double").alias("p50_pvm_moy_3m"),
        F.expr(f"percentile_approx(actual_lt_days, 0.8, {ACC})").cast("double").alias("p80_pvm_moy_3m"),
        F.stddev_samp("actual_lt_days").cast("double").alias("std_pvm_moy_3m"),
        F.avg("actual_lt_days").cast("double").alias("avg_pvm_moy_3m"),
    )
    .withColumnRenamed("target_moy", "moy")
    .persist(StorageLevel.MEMORY_AND_DISK)
)

ft_pv_moy_3m = (
    train_df_3m
    .groupBy(*pv_keys, "target_moy")
    .agg(
        F.count("*").alias("n_pv_moy_3m"),
        F.expr(f"percentile_approx(actual_lt_days, 0.5, {ACC})").cast("double").alias("p50_pv_moy_3m"),
        F.expr(f"percentile_approx(actual_lt_days, 0.8, {ACC})").cast("double").alias("p80_pv_moy_3m"),
        F.stddev_samp("actual_lt_days").cast("double").alias("std_pv_moy_3m"),
        F.avg("actual_lt_days").cast("double").alias("avg_pv_moy_3m"),
    )
    .withColumnRenamed("target_moy", "moy")
    .persist(StorageLevel.MEMORY_AND_DISK)
)

# Planner-style 3M KPI table
by_moy_3m_kpis = (
    train_df_3m
    .groupBy(*keys, "target_moy")
    .agg(
        F.avg("actual_lt_days").alias("avg_actual_lead_time_moy_3m"),
        F.stddev_samp("actual_lt_days").alias("std_deviation_moy_3m"),
        F.count("*").alias("orders_moy_3m"),
        F.expr(f"percentile_approx(actual_lt_days, 0.5, {ACC})").cast("double").alias("p50_actual_lead_time_moy_3m"),
        F.expr(f"percentile_approx(actual_lt_days, 0.8, {ACC})").cast("double").alias("p80_actual_lead_time_moy_3m"),
    )
    .withColumnRenamed("target_moy", "moy")
    .persist(StorageLevel.MEMORY_AND_DISK)
)

log_step("Feature tables ready", extra="pvm_moy, pv_moy, pvm/pv/v, global_moy, pvm_moy_3m, pv_moy_3m")

# =======================
# 5) SCORER (REQ-DATE FREE PREDICTION)
# =======================
def enrich_for_scoring(df_any: DataFrame) -> DataFrame:
    return (
        df_any
        .join(F.broadcast(global_moy), ["moy"], "left")
        .join(F.broadcast(ft_pvm), keys, "left")
        .join(F.broadcast(ft_pvm_moy), keys + ["moy"], "left")
        .join(F.broadcast(ft_pv), pv_keys, "left")
        .join(F.broadcast(ft_pv_moy), pv_keys + ["moy"], "left")
        .join(F.broadcast(ft_v), ["vendor_id"], "left")
    )

def effective_anchor(df: DataFrame) -> DataFrame:
    """
    Anchor = primarily PVM median; fallback PV median; fallback Vendor median; fallback Global
    Then apply Global MOY seasonality delta
    """
    fbk = F.coalesce(F.col("p50_pv"), F.col("p50_v"), F.lit(float(GLOBAL_P50))).cast("double")
    pri = F.col("p50_pvm").cast("double")

    std_fbk = F.coalesce(
        F.col("std_pv"),
        F.col("std_v"),
        F.lit(float(GLOBAL_STD)),
        F.lit(float(STD_FALLBACK))
    ).cast("double")

    std_pri = F.coalesce(F.col("std_pvm"), std_fbk, F.lit(float(STD_FALLBACK))).cast("double")

    primary_bad = (
        pri.isNull() |
        (F.abs(pri - fbk) > F.lit(float(ANCHOR_DIFF_DAYS))) |
        (F.abs(pri - fbk) > F.lit(float(ANCHOR_DIFF_SIGMA)) * std_fbk)
    )

    anchor_base = F.when(primary_bad, fbk).otherwise(pri)
    std_base    = F.when(primary_bad, std_fbk).otherwise(std_pri)

    g_moy_p50 = F.coalesce(F.col("p50_global_moy"), F.lit(float(GLOBAL_P50))).cast("double")
    season_delta = (g_moy_p50 - F.lit(float(GLOBAL_P50))).cast("double")
    anchor_eff = (anchor_base + season_delta).cast("double")

    return (
        df.withColumn("anchor_primary_p50", pri)
          .withColumn("anchor_fallback_p50", fbk)
          .withColumn("anchor_primary_bad", primary_bad.cast("int"))
          .withColumn("season_delta_days", season_delta)
          .withColumn("anchor_eff_p50", anchor_eff)
          .withColumn(
              "std_anchor_eff",
              F.least(
                  F.coalesce(std_base, F.lit(float(STD_FALLBACK))),
                  F.lit(60.0)
              ).cast("double")
          )
    )

def score_planner(df_any: DataFrame) -> DataFrame:
    df = enrich_for_scoring(df_any)
    df = effective_anchor(df)

    unk = is_unknown_material_expr("material_code")

    anchor = F.col("anchor_eff_p50").cast("double")
    std_eff = F.col("std_anchor_eff").cast("double")

    # Existing exact-MOY candidates
    n_pvm_moy   = F.col("n_pvm_moy").cast("double")
    p50_pvm_moy = F.col("p50_pvm_moy").cast("double")

    n_pv_moy    = F.col("n_pv_moy").cast("double")
    p50_pv_moy  = F.col("p50_pv_moy").cast("double")

    sane_pvm_moy = sane_range(p50_pvm_moy, n_pvm_moy, MIN_N_PVM_MOY, anchor, std_eff)
    sane_pv_moy  = sane_range(p50_pv_moy,  n_pv_moy,  MIN_N_PV_MOY,  anchor, std_eff)

    a_pvm_moy = shrink_alpha(n_pvm_moy, TAU)
    a_pv_moy  = shrink_alpha(n_pv_moy, TAU)

    pred_pvm_moy = (a_pvm_moy * p50_pvm_moy + (F.lit(1.0) - a_pvm_moy) * anchor).cast("double")
    pred_pv_moy  = (a_pv_moy  * p50_pv_moy  + (F.lit(1.0) - a_pv_moy)  * anchor).cast("double")

    # Keep existing prediction logic unchanged
    base_pred = (
        F.when(sane_pvm_moy == 1, pred_pvm_moy)
         .when(sane_pv_moy == 1,  pred_pv_moy)
         .otherwise(anchor)
    )

    src = (
        F.when(sane_pvm_moy == 1, F.lit("PVM - Month-specific"))
         .when(sane_pv_moy == 1,  F.lit("PV - Month-specific"))
         .otherwise(F.lit("PVM - Overall history"))
    )

    alpha_used = (
        F.when(sane_pvm_moy == 1, a_pvm_moy)
         .when(sane_pv_moy == 1,  a_pv_moy)
         .otherwise(F.lit(0.0))
    )

    lo = F.greatest(F.lit(float(MIN_LT_DAYS)), anchor - F.lit(float(SEATBELT_SIGMA)) * std_eff)
    hi = F.least(F.lit(float(MAX_LT_DAYS)), anchor + F.lit(float(SEATBELT_SIGMA)) * std_eff)
    pred_p50 = F.least(F.greatest(base_pred, lo), hi)

    pred_p80 = F.least(
        F.greatest(pred_p50 + F.lit(1.28) * std_eff, pred_p50 + F.lit(2.0)),
        F.lit(float(MAX_LT_DAYS))
    )

    conf = (
        F.when(alpha_used >= F.lit(0.70), F.lit("HIGH"))
         .when(alpha_used >= F.lit(0.40), F.lit("MEDIUM"))
         .otherwise(F.lit("LOW"))
    )

    unk_pred = (
        F.coalesce(F.col("p50_pv"), F.col("p50_v"), F.lit(float(GLOBAL_P50))).cast("double")
        + F.col("season_delta_days")
    )

    return (
        df
        .withColumn("pred_p50_days", clamp_days(F.when(unk, unk_pred).otherwise(pred_p50)))
        .withColumn("pred_p80_days", clamp_days(F.when(unk, (unk_pred + F.lit(1.28) * std_eff)).otherwise(pred_p80)))
        .withColumn("pred_src", F.when(unk, F.lit("UNKNOWN_MATERIAL__PV_V_GLOBAL__SEASON")).otherwise(src))
        .withColumn("confidence_score", F.when(unk, F.lit("LOW")).otherwise(conf))
    )

# =======================
# 6) HOLDOUT EVAL (baseline vs model)
# =======================
hold_scored = score_planner(holdout_df).persist(StorageLevel.MEMORY_AND_DISK)
_ = hold_scored.count()

baseline_scored = (
    enrich_for_scoring(holdout_df)
    .transform(effective_anchor)
    .withColumn("pred_p50_days", clamp_days(F.col("anchor_eff_p50")))
    .withColumn("pred_src", F.lit("BASELINE__PVM_ANCHOR_PLUS_GLOBAL_SEASON"))
    .select("actual_lt_days", "pred_p50_days", "pred_src")
)

baseline_eval = baseline_scored.agg(
    F.count("*").alias("n"),
    mae("actual_lt_days", "pred_p50_days"),
    medae("actual_lt_days", "pred_p50_days"),
    rmse("actual_lt_days", "pred_p50_days"),
).withColumn("variant", F.lit("BASELINE"))

model_eval = hold_scored.agg(
    F.count("*").alias("n"),
    mae("actual_lt_days", "pred_p50_days"),
    medae("actual_lt_days", "pred_p50_days"),
    rmse("actual_lt_days", "pred_p50_days"),
).withColumn("variant", F.lit("MODEL"))

display(baseline_eval)
display(model_eval)

eval_by_src = (
    hold_scored.groupBy("pred_src")
    .agg(
        F.count("*").alias("n"),
        mae("actual_lt_days", "pred_p50_days"),
        medae("actual_lt_days", "pred_p50_days"),
        rmse("actual_lt_days", "pred_p50_days"),
    )
    .orderBy(F.desc("n"))
)
display(eval_by_src)

# =======================
# 7) SCENARIO SCORING (today, same-day +1/+2/+3 months)
# =======================
df_items = train_df.select(*keys).distinct().persist(StorageLevel.MEMORY_AND_DISK)
_ = df_items.count()

run = RUN_DATE.cast("date")
m1  = F.add_months(run, 1)
m2  = F.add_months(run, 2)
m3  = F.add_months(run, 3)

scenarios = (
    df_items
    .withColumn("scenario_k", F.explode(F.array(F.lit(0), F.lit(1), F.lit(2), F.lit(3))))
    .withColumn(
        "po_creation_date",
        F.when(F.col("scenario_k") == 0, run)
         .when(F.col("scenario_k") == 1, m1)
         .when(F.col("scenario_k") == 2, m2)
         .otherwise(m3)
    )
    .withColumn("moy", F.month("po_creation_date").cast("int"))
    .persist(StorageLevel.MEMORY_AND_DISK)
)
_ = scenarios.count()

# Attach planner KPIs
sc = (
    scenarios
    .join(F.broadcast(by_moy_kpis), keys + ["moy"], "left")
    .join(F.broadcast(by_moy_3m_kpis), keys + ["moy"], "left")
    .join(
        F.broadcast(
            ft_pvm_moy_3m.select(
                *keys,
                "moy",
                "n_pvm_moy_3m",
                "p50_pvm_moy_3m",
                "p80_pvm_moy_3m",
                "std_pvm_moy_3m",
                "avg_pvm_moy_3m"
            )
        ),
        keys + ["moy"],
        "left"
    )
    .join(
        F.broadcast(
            ft_pv_moy_3m.select(
                *pv_keys,
                "moy",
                "n_pv_moy_3m",
                "p50_pv_moy_3m",
                "p80_pv_moy_3m",
                "std_pv_moy_3m",
                "avg_pv_moy_3m"
            )
        ),
        pv_keys + ["moy"],
        "left"
    )
    .join(F.broadcast(overall_kpis), keys, "left")
)

sc_scored = (
    score_planner(sc)
    .withColumn("eta_pred_date", F.date_add(F.col("po_creation_date"), F.col("pred_p50_days").cast("int")))
    .withColumn("eta_pred_date_p80", F.date_add(F.col("po_creation_date"), F.col("pred_p80_days").cast("int")))
    .persist(StorageLevel.MEMORY_AND_DISK)
)
_ = sc_scored.count()

def wide_max(colname: str, k: int, alias: str):
    return F.max(F.when(F.col("scenario_k") == k, F.col(colname))).alias(alias)

final_eta = (
    sc_scored.groupBy(*keys)
    .agg(
        # ETA p50
        wide_max("eta_pred_date", 0, "eta_current_month"),
        wide_max("eta_pred_date", 1, "eta_month_plus_1"),
        wide_max("eta_pred_date", 2, "eta_month_plus_2"),
        wide_max("eta_pred_date", 3, "eta_month_plus_3"),

        # LT p50
        wide_max("pred_p50_days", 0, "lt_days_current_month"),
        wide_max("pred_p50_days", 1, "lt_days_month_plus_1"),
        wide_max("pred_p50_days", 2, "lt_days_month_plus_2"),
        wide_max("pred_p50_days", 3, "lt_days_month_plus_3"),

        # Source
        wide_max("pred_src", 0, "lt_source_current_month"),
        wide_max("pred_src", 1, "lt_source_month_plus_1"),
        wide_max("pred_src", 2, "lt_source_month_plus_2"),
        wide_max("pred_src", 3, "lt_source_month_plus_3"),

        # LT p80
        wide_max("pred_p80_days", 0, "lt_SAFE_days_current_month"),
        wide_max("pred_p80_days", 1, "lt_SAFE_days_month_plus_1"),
        wide_max("pred_p80_days", 2, "lt_SAFE_days_month_plus_2"),
        wide_max("pred_p80_days", 3, "lt_SAFE_days_month_plus_3"),

        # ETA p80
        wide_max("eta_pred_date_p80", 0, "eta_SAFE_current_month"),
        wide_max("eta_pred_date_p80", 1, "eta_SAFE_month_plus_1"),
        wide_max("eta_pred_date_p80", 2, "eta_SAFE_month_plus_2"),
        wide_max("eta_pred_date_p80", 3, "eta_SAFE_month_plus_3"),

        # Confidence
        wide_max("confidence_score", 0, "confidence_current_month"),
        wide_max("confidence_score", 1, "confidence_month_plus_1"),
        wide_max("confidence_score", 2, "confidence_month_plus_2"),
        wide_max("confidence_score", 3, "confidence_month_plus_3"),

        # Overall KPIs
        F.max("avg_actual_lead_time_overall").alias("avg_actual_lead_time_overall"),
        F.max("std_deviation_overall").alias("std_deviation_overall"),
        F.max("orders_overall").alias("orders_overall"),

        # Existing exact-MOY KPIs
        wide_max("avg_actual_lead_time_moy", 0, "avg_actual_lead_time_PVM_current_month"),
        wide_max("avg_actual_lead_time_moy", 1, "avg_actual_lead_time_PVM_month_plus_1"),
        wide_max("avg_actual_lead_time_moy", 2, "avg_actual_lead_time_PVM_month_plus_2"),
        wide_max("avg_actual_lead_time_moy", 3, "avg_actual_lead_time_PVM_month_plus_3"),

        wide_max("std_deviation_moy", 0, "std_deviation_lead_time_PVM_current_month"),
        wide_max("std_deviation_moy", 1, "std_deviation_lead_time_PVM_month_plus_1"),
        wide_max("std_deviation_moy", 2, "std_deviation_lead_time_PVM_month_plus_2"),
        wide_max("std_deviation_moy", 3, "std_deviation_lead_time_PVM_month_plus_3"),

        wide_max("orders_moy", 0, "orders_PVM_current_month"),
        wide_max("orders_moy", 1, "orders_PVM_month_plus_1"),
        wide_max("orders_moy", 2, "orders_PVM_month_plus_2"),
        wide_max("orders_moy", 3, "orders_PVM_month_plus_3"),

        # New 3M seasonal KPI block
        wide_max("avg_actual_lead_time_moy_3m", 0, "avg_actual_lead_time_PVM_3M_current_month"),
        wide_max("avg_actual_lead_time_moy_3m", 1, "avg_actual_lead_time_PVM_3M_month_plus_1"),
        wide_max("avg_actual_lead_time_moy_3m", 2, "avg_actual_lead_time_PVM_3M_month_plus_2"),
        wide_max("avg_actual_lead_time_moy_3m", 3, "avg_actual_lead_time_PVM_3M_month_plus_3"),

        wide_max("std_deviation_moy_3m", 0, "std_deviation_lead_time_PVM_3M_current_month"),
        wide_max("std_deviation_moy_3m", 1, "std_deviation_lead_time_PVM_3M_month_plus_1"),
        wide_max("std_deviation_moy_3m", 2, "std_deviation_lead_time_PVM_3M_month_plus_2"),
        wide_max("std_deviation_moy_3m", 3, "std_deviation_lead_time_PVM_3M_month_plus_3"),

        wide_max("orders_moy_3m", 0, "orders_PVM_3M_current_month"),
        wide_max("orders_moy_3m", 1, "orders_PVM_3M_month_plus_1"),
        wide_max("orders_moy_3m", 2, "orders_PVM_3M_month_plus_2"),
        wide_max("orders_moy_3m", 3, "orders_PVM_3M_month_plus_3"),

        wide_max("p50_actual_lead_time_moy_3m", 0, "p50_actual_lead_time_PVM_3M_current_month"),
        wide_max("p50_actual_lead_time_moy_3m", 1, "p50_actual_lead_time_PVM_3M_month_plus_1"),
        wide_max("p50_actual_lead_time_moy_3m", 2, "p50_actual_lead_time_PVM_3M_month_plus_2"),
        wide_max("p50_actual_lead_time_moy_3m", 3, "p50_actual_lead_time_PVM_3M_month_plus_3"),

        wide_max("p80_actual_lead_time_moy_3m", 0, "p80_actual_lead_time_PVM_3M_current_month"),
        wide_max("p80_actual_lead_time_moy_3m", 1, "p80_actual_lead_time_PVM_3M_month_plus_1"),
        wide_max("p80_actual_lead_time_moy_3m", 2, "p80_actual_lead_time_PVM_3M_month_plus_2"),
        wide_max("p80_actual_lead_time_moy_3m", 3, "p80_actual_lead_time_PVM_3M_month_plus_3"),

        # Raw 3M seasonal stats block
        wide_max("n_pvm_moy_3m", 0, "n_PVM_3M_current_month"),
        wide_max("n_pvm_moy_3m", 1, "n_PVM_3M_month_plus_1"),
        wide_max("n_pvm_moy_3m", 2, "n_PVM_3M_month_plus_2"),
        wide_max("n_pvm_moy_3m", 3, "n_PVM_3M_month_plus_3"),

        wide_max("p50_pvm_moy_3m", 0, "p50_PVM_3M_current_month"),
        wide_max("p50_pvm_moy_3m", 1, "p50_PVM_3M_month_plus_1"),
        wide_max("p50_pvm_moy_3m", 2, "p50_PVM_3M_month_plus_2"),
        wide_max("p50_pvm_moy_3m", 3, "p50_PVM_3M_month_plus_3"),

        wide_max("p80_pvm_moy_3m", 0, "p80_PVM_3M_current_month"),
        wide_max("p80_pvm_moy_3m", 1, "p80_PVM_3M_month_plus_1"),
        wide_max("p80_pvm_moy_3m", 2, "p80_PVM_3M_month_plus_2"),
        wide_max("p80_pvm_moy_3m", 3, "p80_PVM_3M_month_plus_3"),

        wide_max("std_pvm_moy_3m", 0, "std_PVM_3M_current_month"),
        wide_max("std_pvm_moy_3m", 1, "std_PVM_3M_month_plus_1"),
        wide_max("std_pvm_moy_3m", 2, "std_PVM_3M_month_plus_2"),
        wide_max("std_pvm_moy_3m", 3, "std_PVM_3M_month_plus_3"),

        wide_max("avg_pvm_moy_3m", 0, "avg_PVM_3M_current_month"),
        wide_max("avg_pvm_moy_3m", 1, "avg_PVM_3M_month_plus_1"),
        wide_max("avg_pvm_moy_3m", 2, "avg_PVM_3M_month_plus_2"),
        wide_max("avg_pvm_moy_3m", 3, "avg_PVM_3M_month_plus_3"),

        # Optional PV 3M raw stats block
        wide_max("n_pv_moy_3m", 0, "n_PV_3M_current_month"),
        wide_max("n_pv_moy_3m", 1, "n_PV_3M_month_plus_1"),
        wide_max("n_pv_moy_3m", 2, "n_PV_3M_month_plus_2"),
        wide_max("n_pv_moy_3m", 3, "n_PV_3M_month_plus_3"),

        wide_max("p50_pv_moy_3m", 0, "p50_PV_3M_current_month"),
        wide_max("p50_pv_moy_3m", 1, "p50_PV_3M_month_plus_1"),
        wide_max("p50_pv_moy_3m", 2, "p50_PV_3M_month_plus_2"),
        wide_max("p50_pv_moy_3m", 3, "p50_PV_3M_month_plus_3"),

        wide_max("p80_pv_moy_3m", 0, "p80_PV_3M_current_month"),
        wide_max("p80_pv_moy_3m", 1, "p80_PV_3M_month_plus_1"),
        wide_max("p80_pv_moy_3m", 2, "p80_PV_3M_month_plus_2"),
        wide_max("p80_pv_moy_3m", 3, "p80_PV_3M_month_plus_3"),

        wide_max("std_pv_moy_3m", 0, "std_PV_3M_current_month"),
        wide_max("std_pv_moy_3m", 1, "std_PV_3M_month_plus_1"),
        wide_max("std_pv_moy_3m", 2, "std_PV_3M_month_plus_2"),
        wide_max("std_pv_moy_3m", 3, "std_PV_3M_month_plus_3"),

        wide_max("avg_pv_moy_3m", 0, "avg_PV_3M_current_month"),
        wide_max("avg_pv_moy_3m", 1, "avg_PV_3M_month_plus_1"),
        wide_max("avg_pv_moy_3m", 2, "avg_PV_3M_month_plus_2"),
        wide_max("avg_pv_moy_3m", 3, "avg_PV_3M_month_plus_3"),
    )
    .persist(StorageLevel.MEMORY_AND_DISK)
)
_ = final_eta.count()




supplier_risk = (
    df_done_stats
    .groupBy("vendor_id")
    .agg(
        F.count("*").alias("supplier_total_orders"),
        F.sum(
            F.when(
                F.col("outlier_severity") == "EXTREME_OUTLIER",
                1
            ).otherwise(0)
        ).alias("supplier_extreme_events")
    )
    .withColumn(
        "supplier_extreme_event_rate",
        F.col("supplier_extreme_events") / F.col("supplier_total_orders")
    )
)

final_clean = (
    final_eta
    .join(pv_rel, pv_keys, "left")
    .join(ft_pv.select(*pv_keys, "n_pv", "p50_pv", "p80_pv", "std_pv"), pv_keys, "left")
    .join(ft_v.select("vendor_id", "n_v", "p50_v", "p80_v", "std_v"), ["vendor_id"], "left")
    .join(supplier_risk, ["vendor_id"], "left")

    # Supplier reliability metrics
    .withColumn("supplier_history_n", F.col("n_v").cast("long"))
    .withColumn("supplier_p50_lead_time_days", F.col("p50_v").cast("double"))
    .withColumn("supplier_p80_lead_time_days", F.col("p80_v").cast("double"))
    .withColumn("supplier_std_deviation_days", F.col("std_v").cast("double"))

    # CV = std / p50
    .withColumn(
        "supplier_cv",
        F.when(
            F.col("p50_v").isNotNull() & (F.col("p50_v") > 0) & F.col("std_v").isNotNull(),
            (F.col("std_v") / F.col("p50_v")).cast("double")
        ).otherwise(F.lit(None).cast("double"))
    )

    # Std-based class
    .withColumn(
        "supplier_class_std",
        classify_supplier_std(F.col("std_v"), F.col("n_v"))
    )
    .withColumn(
        "supplier_class_std_interpretation",
        interpret_supplier_class(F.col("supplier_class_std"))
    )

    # CV-based class
    .withColumn(
        "supplier_class_cv",
        classify_supplier_cv(F.col("supplier_cv"), F.col("n_v"))
    )
    .withColumn(
        "supplier_class_cv_interpretation",
        interpret_supplier_class(F.col("supplier_class_cv"))
    )

    # Recommended business-facing class
    .withColumn("supplier_class_recommended", F.col("supplier_class_cv"))
    .withColumn("supplier_class_recommended_interpretation", F.col("supplier_class_cv_interpretation"))

    # Supplier disruption risk based on extreme outlier frequency
    .withColumn(
        "supplier_risk_level",
        F.when(F.col("supplier_extreme_event_rate").isNull(), F.lit("UNKNOWN"))
         .when(F.col("supplier_extreme_event_rate") < 0.02, F.lit("LOW"))
         .when(F.col("supplier_extreme_event_rate") < 0.10, F.lit("MEDIUM"))
         .otherwise(F.lit("HIGH"))
    )

    .withColumn(
        "variant_name",
        F.lit(
            f"PLANNER_SCORER__TAU_{TAU}__SANITY_{SANITY_SIGMA}__SEATBELT_{SEATBELT_SIGMA}__ADAYS_{ANCHOR_DIFF_DAYS}__3Y__LEAKAGE_SAFE__WITH_3M_STATS__WITH_SUPPLIER_CLASS__WITH_OUTLIER_SEVERITY"
        )
    )
    .withColumn(
        "supplier_variability_category",
        F.when(
            (F.col("supplier_cv") < 0.5) & (F.col("supplier_std_deviation_days") < 20),
            "Stable Supplier"
        )
        .when(
            (F.col("supplier_cv") >= 0.5) & (F.col("supplier_std_deviation_days") < 20),
            "Short Lead Time but Variable"
        )
        .when(
            (F.col("supplier_cv") < 0.5) & (F.col("supplier_std_deviation_days") >= 20),
            "Long but Predictable Lead Time"
        )
        .otherwise("High Variability Supplier")
    )
    .persist(StorageLevel.MEMORY_AND_DISK)
)

_ = final_clean.count()
display(final_clean)

src_counts = sc_scored.groupBy("pred_src").count().orderBy(F.desc("count"))
display(src_counts)

# COMMAND ----------

# DBTITLE 1,Supplier Reliability (per plant)
from pyspark.sql import functions as F

# ==========================================================
# SUPPLIER SUMMARY - OVERALL + PER PLANT
# plant_code_scope = 'All'  -> supplier overall
# plant_code_scope = actual plant code -> supplier within plant
#
# Design:
# - *_all                  => computed on full history (with outliers)
# - *_wo_outliers          => computed excluding confirmed outliers only
#                             (NORMAL + MILD_OUTLIER + UNKNOWN kept)
# - extreme event metrics  => computed on full history
# - recommended class      => based on wo_outliers version
# ==========================================================

supplier_base_all = (
    df_done_stats
    .select(
        "vendor_id",
        "plant_code",
        "actual_lt_days",
        "outlier_severity"
    )
    .filter(F.col("vendor_id").isNotNull())
    .filter(F.col("plant_code").isNotNull())
)

# FIX: Include UNKNOWN severity — these are orders where MAD could not
# be computed (insufficient data at KEY/PV/V level for outlier detection).
# They are NOT confirmed outliers; excluding them caused ~65% of suppliers
# to fall into INSUFFICIENT_HISTORY despite having many total orders.
supplier_base_wo = (
    supplier_base_all
    .filter(F.col("outlier_severity").isin("NORMAL", "MILD_OUTLIER", "UNKNOWN"))
)

# ----------------------------------------------------------
# Helper to compute lead time distribution stats
# ----------------------------------------------------------
def build_supplier_stats(df, scope_col_name="plant_code_scope", overall=False):
    if overall:
        return (
            df.groupBy("vendor_id")
            .agg(
                F.count("*").alias("supplier_history_n"),
                F.expr(f"percentile_approx(actual_lt_days, 0.5, {ACC})").cast("double").alias("supplier_p50_lead_time_days"),
                F.expr(f"percentile_approx(actual_lt_days, 0.8, {ACC})").cast("double").alias("supplier_p80_lead_time_days"),
                F.stddev_samp("actual_lt_days").cast("double").alias("supplier_std_deviation_days"),
            )
            .withColumn(scope_col_name, F.lit("All"))
        )
    else:
        return (
            df.groupBy("vendor_id", "plant_code")
            .agg(
                F.count("*").alias("supplier_history_n"),
                F.expr(f"percentile_approx(actual_lt_days, 0.5, {ACC})").cast("double").alias("supplier_p50_lead_time_days"),
                F.expr(f"percentile_approx(actual_lt_days, 0.8, {ACC})").cast("double").alias("supplier_p80_lead_time_days"),
                F.stddev_samp("actual_lt_days").cast("double").alias("supplier_std_deviation_days"),
            )
            .withColumnRenamed("plant_code", scope_col_name)
        )

# ----------------------------------------------------------
# 1) ALL-HISTORY stats (with outliers)
# ----------------------------------------------------------
supplier_summary_all_allhist = build_supplier_stats(
    supplier_base_all,
    scope_col_name="plant_code_scope",
    overall=True
)

supplier_summary_plant_allhist = build_supplier_stats(
    supplier_base_all,
    scope_col_name="plant_code_scope",
    overall=False
)

supplier_stats_allhist = (
    supplier_summary_all_allhist
    .unionByName(supplier_summary_plant_allhist)
    .withColumnRenamed("supplier_history_n", "supplier_history_n_all")
    .withColumnRenamed("supplier_p50_lead_time_days", "supplier_p50_lead_time_days_all")
    .withColumnRenamed("supplier_p80_lead_time_days", "supplier_p80_lead_time_days_all")
    .withColumnRenamed("supplier_std_deviation_days", "supplier_std_deviation_days_all")
)

# ----------------------------------------------------------
# 2) WITHOUT-OUTLIERS stats
# ----------------------------------------------------------
supplier_summary_all_wo = build_supplier_stats(
    supplier_base_wo,
    scope_col_name="plant_code_scope",
    overall=True
)

supplier_summary_plant_wo = build_supplier_stats(
    supplier_base_wo,
    scope_col_name="plant_code_scope",
    overall=False
)

supplier_stats_wo = (
    supplier_summary_all_wo
    .unionByName(supplier_summary_plant_wo)
    .withColumnRenamed("supplier_history_n", "supplier_history_n_wo_outliers")
    .withColumnRenamed("supplier_p50_lead_time_days", "supplier_p50_lead_time_days_wo_outliers")
    .withColumnRenamed("supplier_p80_lead_time_days", "supplier_p80_lead_time_days_wo_outliers")
    .withColumnRenamed("supplier_std_deviation_days", "supplier_std_deviation_days_wo_outliers")
)

# ----------------------------------------------------------
# 3) FULL-HISTORY risk metrics
# ----------------------------------------------------------
supplier_risk_all = (
    supplier_base_all
    .groupBy("vendor_id")
    .agg(
        F.count("*").alias("supplier_total_orders"),
        F.sum(F.when(F.col("outlier_severity") == "EXTREME_OUTLIER", 1).otherwise(0)).alias("supplier_extreme_events")
    )
    .withColumn("plant_code_scope", F.lit("All"))
)

supplier_risk_plant = (
    supplier_base_all
    .groupBy("vendor_id", "plant_code")
    .agg(
        F.count("*").alias("supplier_total_orders"),
        F.sum(F.when(F.col("outlier_severity") == "EXTREME_OUTLIER", 1).otherwise(0)).alias("supplier_extreme_events")
    )
    .withColumnRenamed("plant_code", "plant_code_scope")
)

supplier_risk = (
    supplier_risk_all
    .unionByName(supplier_risk_plant)
    .withColumn(
        "supplier_extreme_event_rate",
        F.when(
            F.col("supplier_total_orders") > 0,
            F.col("supplier_extreme_events") / F.col("supplier_total_orders")
        ).otherwise(F.lit(None).cast("double"))
    )
)

# ----------------------------------------------------------
# 4) Join all together
# ----------------------------------------------------------
supplier_summary_per_plant = (
    supplier_stats_allhist
    .join(
        supplier_stats_wo,
        ["vendor_id", "plant_code_scope"],
        "full"
    )
    .join(
        supplier_risk,
        ["vendor_id", "plant_code_scope"],
        "left"
    )

    # ------------------------------------------------------
    # CV metrics - ALL HISTORY
    # ------------------------------------------------------
    .withColumn(
        "supplier_cv_all",
        F.when(
            F.col("supplier_p50_lead_time_days_all").isNotNull() &
            (F.col("supplier_p50_lead_time_days_all") > 0) &
            F.col("supplier_std_deviation_days_all").isNotNull(),
            (F.col("supplier_std_deviation_days_all") / F.col("supplier_p50_lead_time_days_all")).cast("double")
        ).otherwise(F.lit(None).cast("double"))
    )

    # ------------------------------------------------------
    # CV metrics - WITHOUT OUTLIERS
    # ------------------------------------------------------
    .withColumn(
        "supplier_cv_wo_outliers",
        F.when(
            F.col("supplier_p50_lead_time_days_wo_outliers").isNotNull() &
            (F.col("supplier_p50_lead_time_days_wo_outliers") > 0) &
            F.col("supplier_std_deviation_days_wo_outliers").isNotNull(),
            (F.col("supplier_std_deviation_days_wo_outliers") / F.col("supplier_p50_lead_time_days_wo_outliers")).cast("double")
        ).otherwise(F.lit(None).cast("double"))
    )

    # ------------------------------------------------------
    # STD classes - ALL HISTORY
    # ------------------------------------------------------
    .withColumn(
        "supplier_class_std_all",
        classify_supplier_std(
            F.col("supplier_std_deviation_days_all"),
            F.col("supplier_history_n_all")
        )
    )
    .withColumn(
        "supplier_class_std_all_interpretation",
        interpret_supplier_class(F.col("supplier_class_std_all"))
    )

    # ------------------------------------------------------
    # CV classes - ALL HISTORY
    # ------------------------------------------------------
    .withColumn(
        "supplier_class_cv_all",
        classify_supplier_cv(
            F.col("supplier_cv_all"),
            F.col("supplier_history_n_all")
        )
    )
    .withColumn(
        "supplier_class_cv_all_interpretation",
        interpret_supplier_class(F.col("supplier_class_cv_all"))
    )

    # ------------------------------------------------------
    # STD classes - WITHOUT OUTLIERS
    # ------------------------------------------------------
    .withColumn(
        "supplier_class_std_wo_outliers",
        classify_supplier_std(
            F.col("supplier_std_deviation_days_wo_outliers"),
            F.col("supplier_history_n_wo_outliers")
        )
    )
    .withColumn(
        "supplier_class_std_wo_outliers_interpretation",
        interpret_supplier_class(F.col("supplier_class_std_wo_outliers"))
    )

    # ------------------------------------------------------
    # CV classes - WITHOUT OUTLIERS
    # ------------------------------------------------------
    .withColumn(
        "supplier_class_cv_wo_outliers",
        classify_supplier_cv(
            F.col("supplier_cv_wo_outliers"),
            F.col("supplier_history_n_wo_outliers")
        )
    )
    .withColumn(
        "supplier_class_cv_wo_outliers_interpretation",
        interpret_supplier_class(F.col("supplier_class_cv_wo_outliers"))
    )

    # ------------------------------------------------------
    # Recommended class -> WITHOUT OUTLIERS
    # ------------------------------------------------------
    .withColumn("supplier_class_recommended", F.col("supplier_class_cv_wo_outliers"))
    .withColumn("supplier_class_recommended_interpretation", F.col("supplier_class_cv_wo_outliers_interpretation"))

    # ------------------------------------------------------
    # Risk level -> FULL HISTORY EXTREME EVENT RATE
    # ------------------------------------------------------
    .withColumn(
        "supplier_risk_level",
        F.when(F.col("supplier_extreme_event_rate").isNull(), F.lit("UNKNOWN"))
         .when(F.col("supplier_extreme_event_rate") < 0.02, F.lit("LOW"))
         .when(F.col("supplier_extreme_event_rate") < 0.10, F.lit("MEDIUM"))
         .otherwise(F.lit("HIGH"))
    )

    # ------------------------------------------------------
    # Variability category - ALL HISTORY
    # ------------------------------------------------------
    .withColumn(
        "supplier_variability_category_all",
        F.when(
            (F.col("supplier_cv_all") < 0.5) & (F.col("supplier_std_deviation_days_all") < 20),
            "Stable Supplier"
        )
        .when(
            (F.col("supplier_cv_all") >= 0.5) & (F.col("supplier_std_deviation_days_all") < 20),
            "Short Lead Time but Variable"
        )
        .when(
            (F.col("supplier_cv_all") < 0.5) & (F.col("supplier_std_deviation_days_all") >= 20),
            "Long but Predictable Lead Time"
        )
        .otherwise("High Variability Supplier")
    )

    # ------------------------------------------------------
    # Variability category - WITHOUT OUTLIERS
    # ------------------------------------------------------
    .withColumn(
        "supplier_variability_category_wo_outliers",
        F.when(
            (F.col("supplier_cv_wo_outliers") < 0.5) & (F.col("supplier_std_deviation_days_wo_outliers") < 20),
            "Stable Supplier"
        )
        .when(
            (F.col("supplier_cv_wo_outliers") >= 0.5) & (F.col("supplier_std_deviation_days_wo_outliers") < 20),
            "Short Lead Time but Variable"
        )
        .when(
            (F.col("supplier_cv_wo_outliers") < 0.5) & (F.col("supplier_std_deviation_days_wo_outliers") >= 20),
            "Long but Predictable Lead Time"
        )
        .otherwise("High Variability Supplier")
    )

    # recommended business-facing variability category
    .withColumn(
        "supplier_variability_category_recommended",
        F.col("supplier_variability_category_wo_outliers")
    )

    .dropDuplicates(["vendor_id", "plant_code_scope"])
)

# ----------------------------------------------------------
# 5) Enrich with vendor dimension (vendor_key + vendor_name)
# ----------------------------------------------------------
_vendor_dim = (
    spark.table(f"{full_schema}.{MDP_DATA}")
    .select("vendor_id", "vendor_key", "vendor_name")
    .dropDuplicates(["vendor_id"])
)

supplier_summary_per_plant = (
    supplier_summary_per_plant
    .join(_vendor_dim, "vendor_id", "left")
)

# COMMAND ----------

# DBTITLE 1,Supplier Reliability (overall)
# ============================================================
# Derive supplier_summary from supplier_summary_per_plant (All)
# so that Supplier_Reliability == per_plant "All" row by design
# ============================================================
supplier_summary = (
    supplier_summary_per_plant
    .filter(F.col("plant_code_scope") == "All")
    .drop("plant_code_scope")

    # Rename _wo_outliers -> non-suffixed (main reliability view)
    .withColumnRenamed("supplier_history_n_wo_outliers", "supplier_history_n")
    .withColumnRenamed("supplier_p50_lead_time_days_wo_outliers", "supplier_p50_lead_time_days")
    .withColumnRenamed("supplier_p80_lead_time_days_wo_outliers", "supplier_p80_lead_time_days")
    .withColumnRenamed("supplier_std_deviation_days_wo_outliers", "supplier_std_deviation_days")
    .withColumnRenamed("supplier_cv_wo_outliers", "supplier_cv")
    .withColumnRenamed("supplier_class_std_wo_outliers", "supplier_class_std")
    .withColumnRenamed("supplier_class_std_wo_outliers_interpretation", "supplier_class_std_interpretation")
    .withColumnRenamed("supplier_class_cv_wo_outliers", "supplier_class_cv")
    .withColumnRenamed("supplier_class_cv_wo_outliers_interpretation", "supplier_class_cv_interpretation")
    .withColumnRenamed("supplier_variability_category_wo_outliers", "supplier_variability_category")

    .dropDuplicates(["vendor_id"])
)



from pyspark.sql import functions as F
from pyspark.storagelevel import StorageLevel
import pandas as pd
import plotly.express as px

# ============================================
# SUPPLIER REVIEW PLOTS - ONE CELL
# Works from: supplier_summary
# ============================================

# -----------------------
# 0) Prepare clean supplier-level dataset
# -----------------------
plot_df = (
    supplier_summary
    .select(
        "vendor_id",
        "supplier_history_n",
        "supplier_p50_lead_time_days",
        "supplier_p80_lead_time_days",
        "supplier_std_deviation_days",
        "supplier_cv",
        "supplier_class_std",
        "supplier_class_cv",
        "supplier_class_recommended",
        "supplier_risk_level",
        "supplier_variability_category",
        "supplier_extreme_event_rate"
    )
    .dropDuplicates(["vendor_id"])
    .filter(F.col("vendor_id").isNotNull())
    .withColumn(
        "supplier_variability_category_plot",
        F.when(F.col("supplier_variability_category") == "High Risk Supplier", F.lit("High Variability Supplier"))
         .otherwise(F.col("supplier_variability_category"))
    )
    .persist(StorageLevel.MEMORY_AND_DISK)
)

# Optional: inspect count
print(f"Suppliers in plot_df: {plot_df.count()}")

# Thresholds used in your logic
CV_THRESHOLD = 0.50
STD_THRESHOLD = 20.0

# -----------------------
# 1) STD Histogram
# -----------------------
std_pd = (
    plot_df
    .select("supplier_std_deviation_days")
    .filter(F.col("supplier_std_deviation_days").isNotNull())
    .toPandas()
)

fig_std = px.histogram(
    std_pd,
    x="supplier_std_deviation_days",
    nbins=50,
    title="Supplier Lead Time Variability - Std Deviation Distribution"
)
fig_std.add_vline(x=10, line_dash="dash", line_color="green")
fig_std.add_vline(x=25, line_dash="dash", line_color="orange")
fig_std.add_vline(x=45, line_dash="dash", line_color="red")
fig_std.update_layout(
    xaxis_title="Supplier std deviation (days)",
    yaxis_title="Supplier count"
)
fig_std.show()

# -----------------------
# 2) CV Histogram
# -----------------------
cv_pd = (
    plot_df
    .select("supplier_cv")
    .filter(F.col("supplier_cv").isNotNull())
    .toPandas()
)

fig_cv = px.histogram(
    cv_pd,
    x="supplier_cv",
    nbins=50,
    title="Supplier Lead Time Variability - CV Distribution"
)
fig_cv.add_vline(x=0.10, line_dash="dash", line_color="green")
fig_cv.add_vline(x=0.25, line_dash="dash", line_color="orange")
fig_cv.add_vline(x=0.50, line_dash="dash", line_color="red")
fig_cv.update_layout(
    xaxis_title="Supplier coefficient of variation (CV)",
    yaxis_title="Supplier count"
)
fig_cv.show()

# -----------------------
# 3) CV vs STD Scatter
# -----------------------
scatter_pd = (
    plot_df
    .select(
        "supplier_cv",
        "supplier_std_deviation_days",
        "supplier_variability_category_plot",
        "supplier_risk_level",
        "supplier_history_n",
        "supplier_p50_lead_time_days",
        "supplier_extreme_event_rate"
    )
    .filter(F.col("supplier_cv").isNotNull() & F.col("supplier_std_deviation_days").isNotNull())
    .toPandas()
)

fig_scatter = px.scatter(
    scatter_pd,
    x="supplier_cv",
    y="supplier_std_deviation_days",
    color="supplier_variability_category_plot",
    hover_data=[
        "supplier_risk_level",
        "supplier_history_n",
        "supplier_p50_lead_time_days",
        "supplier_extreme_event_rate"
    ],
    title="Supplier Variability Profile - CV vs Std Deviation",
    opacity=0.7
)
fig_scatter.add_vline(x=CV_THRESHOLD, line_dash="dash", line_color="red")
fig_scatter.add_hline(y=STD_THRESHOLD, line_dash="dash", line_color="red")
fig_scatter.update_layout(
    xaxis_title="Supplier CV",
    yaxis_title="Supplier std deviation (days)",
    legend_title="Variability category"
)
fig_scatter.show()

# -----------------------
# 4) Variability Category Distribution (%)
# -----------------------
total_suppliers = plot_df.select("vendor_id").distinct().count()

cat_dist_pd = (
    plot_df
    .groupBy("supplier_variability_category_plot")
    .agg(F.count("*").alias("supplier_count"))
    .withColumn("percentage", F.col("supplier_count") / F.lit(total_suppliers) * 100.0)
    .orderBy(F.desc("supplier_count"))
    .toPandas()
)

fig_cat = px.bar(
    cat_dist_pd,
    x="supplier_variability_category_plot",
    y="percentage",
    text="percentage",
    title="Supplier Variability Category Distribution (%)"
)
fig_cat.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
fig_cat.update_layout(
    xaxis_title="Variability category",
    yaxis_title="Percentage of suppliers"
)
fig_cat.show()

# -----------------------
# 5) Disruption Risk Distribution (%)
# -----------------------
risk_dist_pd = (
    plot_df
    .groupBy("supplier_risk_level")
    .agg(F.count("*").alias("supplier_count"))
    .withColumn("percentage", F.col("supplier_count") / F.lit(total_suppliers) * 100.0)
    .orderBy(F.desc("supplier_count"))
    .toPandas()
)

fig_risk = px.bar(
    risk_dist_pd,
    x="supplier_risk_level",
    y="percentage",
    text="percentage",
    title="Supplier Disruption Risk Distribution (%)"
)
fig_risk.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
fig_risk.update_layout(
    xaxis_title="Disruption risk level",
    yaxis_title="Percentage of suppliers"
)
fig_risk.show()

# -----------------------
# 6) Variability Category vs Disruption Risk
# -----------------------
cross_pd = (
    plot_df
    .groupBy("supplier_variability_category_plot", "supplier_risk_level")
    .agg(F.count("*").alias("supplier_count"))
    .toPandas()
)

fig_cross = px.bar(
    cross_pd,
    x="supplier_variability_category_plot",
    y="supplier_count",
    color="supplier_risk_level",
    barmode="stack",
    title="Variability Category vs Disruption Risk"
)
fig_cross.update_layout(
    xaxis_title="Variability category",
    yaxis_title="Supplier count",
    legend_title="Disruption risk level"
)
fig_cross.show()

# -----------------------
# 7) Extreme Event Rate Histogram
# -----------------------
eer_pd = (
    plot_df
    .select("supplier_extreme_event_rate")
    .filter(F.col("supplier_extreme_event_rate").isNotNull())
    .toPandas()
)

fig_eer = px.histogram(
    eer_pd,
    x="supplier_extreme_event_rate",
    nbins=50,
    title="Supplier Extreme Event Rate Distribution"
)
fig_eer.add_vline(x=0.02, line_dash="dash", line_color="green")
fig_eer.add_vline(x=0.10, line_dash="dash", line_color="red")
fig_eer.update_layout(
    xaxis_title="Extreme event rate",
    yaxis_title="Supplier count"
)
fig_eer.show()

# -----------------------
# 8) Top suppliers by std deviation
# -----------------------
top_std_pd = (
    plot_df
    .select(
        "vendor_id",
        "supplier_std_deviation_days",
        "supplier_cv",
        "supplier_risk_level",
        "supplier_variability_category_plot"
    )
    .orderBy(F.desc("supplier_std_deviation_days"))
    .limit(20)
    .toPandas()
)

fig_top_std = px.bar(
    top_std_pd,
    x="vendor_id",
    y="supplier_std_deviation_days",
    color="supplier_variability_category_plot",
    hover_data=["supplier_cv", "supplier_risk_level"],
    title="Top 20 Suppliers by Std Deviation"
)
fig_top_std.update_layout(
    xaxis_title="Vendor ID",
    yaxis_title="Std deviation (days)",
    legend_title="Variability category"
)
fig_top_std.show()

# -----------------------
# 9) Top suppliers by extreme event rate
# -----------------------
top_eer_pd = (
    plot_df
    .select(
        "vendor_id",
        "supplier_extreme_event_rate",
        "supplier_std_deviation_days",
        "supplier_cv",
        "supplier_risk_level"
    )
    .orderBy(F.desc("supplier_extreme_event_rate"))
    .limit(20)
    .toPandas()
)

fig_top_eer = px.bar(
    top_eer_pd,
    x="vendor_id",
    y="supplier_extreme_event_rate",
    color="supplier_risk_level",
    hover_data=["supplier_std_deviation_days", "supplier_cv"],
    title="Top 20 Suppliers by Extreme Event Rate"
)
fig_top_eer.update_layout(
    xaxis_title="Vendor ID",
    yaxis_title="Extreme event rate",
    legend_title="Disruption risk level"
)
fig_top_eer.show()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Save

# COMMAND ----------

final_clean = final_clean.withColumn(
    "material_code",
    F.regexp_replace("material_code", r"^0+", "")
)

# COMMAND ----------

# DBTITLE 1,add keys
# Join back surrogate keys from df0 (1:1 mapping via keys)
# Strip leading zeros from material_code to match final_clean (Cell 28)
dim_keys_df = (
    df0
    .select("plant_code", "vendor_id", "material_code",
            "vendor_key", "plant_key", "material_key", "material_plant_key")
    .withColumn("material_code", F.regexp_replace("material_code", r"^0+", ""))
    .distinct()
)

final_with_keys = final_clean.join(dim_keys_df, ["plant_code", "vendor_id", "material_code"], "left")

# COMMAND ----------

final_with_keys.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{GOLD}.Lead_Time_Forecasts_statistics")

# COMMAND ----------

supplier_summary.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{GOLD}.Supplier_Reliability"
)

# COMMAND ----------

supplier_summary_per_plant.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{GOLD}.Supplier_Reliability_per_Plant"
)
