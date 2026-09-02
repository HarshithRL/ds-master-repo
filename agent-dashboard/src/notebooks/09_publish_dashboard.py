# Databricks notebook source
# MAGIC %run ./config_file

# COMMAND ----------

# MAGIC %python
# MAGIC spark.sql(f"USE CATALOG {UNITY_CATALOG}")
# MAGIC print(f"Active catalog: {UNITY_CATALOG}")

# COMMAND ----------
# DBTITLE 1,Publish Dashboard
# MAGIC %md
# MAGIC # Publish Silver Dashboard
# MAGIC
# MAGIC Runs only after Validate_dashboard succeeds.
# MAGIC Pre-checks draft for stale catalog refs, then publishes Lakeview dashboard
# MAGIC `01f19237ae0419ea830abdda6219869d` (Agent Dashboard Phase 1 Silver).

# COMMAND ----------

# DBTITLE 1,Config
# MAGIC %python
# MAGIC dbutils.widgets.text("dashboard_id", DEFAULT_DASHBOARD_ID)
# MAGIC dbutils.widgets.text("warehouse_id", DEFAULT_WAREHOUSE_ID)
# MAGIC DASHBOARD_ID = dbutils.widgets.get("dashboard_id") or DEFAULT_DASHBOARD_ID
# MAGIC WAREHOUSE_ID = dbutils.widgets.get("warehouse_id") or DEFAULT_WAREHOUSE_ID
# MAGIC print(f"dashboard_id = {DASHBOARD_ID}")
# MAGIC print(f"warehouse_id = {WAREHOUSE_ID}")
# MAGIC print(f"catalog       = {UNITY_CATALOG}")

# COMMAND ----------

# DBTITLE 1,Pre-publish Deploy Check
# MAGIC %python
# MAGIC import json
# MAGIC import re
# MAGIC from databricks.sdk import WorkspaceClient
# MAGIC
# MAGIC w = WorkspaceClient()
# MAGIC
# MAGIC def _lakeview_get(dashboard_id: str):
# MAGIC     """Compatible with older cluster SDKs that lack lakeview.get."""
# MAGIC     if hasattr(w.lakeview, "get"):
# MAGIC         return w.lakeview.get(dashboard_id)
# MAGIC     # REST fallback
# MAGIC     return w.api_client.do("GET", f"/api/2.0/lakeview/dashboards/{dashboard_id}")
# MAGIC
# MAGIC draft = _lakeview_get(DASHBOARD_ID)
# MAGIC if isinstance(draft, dict):
# MAGIC     ser_raw = draft.get("serialized_dashboard")
# MAGIC     display_name = draft.get("display_name")
# MAGIC     lifecycle_state = draft.get("lifecycle_state")
# MAGIC else:
# MAGIC     ser_raw = draft.serialized_dashboard
# MAGIC     display_name = getattr(draft, "display_name", None)
# MAGIC     lifecycle_state = getattr(draft, "lifecycle_state", None)
# MAGIC
# MAGIC if isinstance(ser_raw, str):
# MAGIC     ser = json.loads(ser_raw)
# MAGIC     ser_text = ser_raw
# MAGIC else:
# MAGIC     ser = ser_raw if isinstance(ser_raw, dict) else json.loads(json.dumps(ser_raw))
# MAGIC     ser_text = json.dumps(ser)
# MAGIC
# MAGIC stale_genie = sorted(set(re.findall(r"general_d\.aladdin_genie\.\w+", ser_text)))
# MAGIC # Flag bronze refs in any env catalog (automation_d/a/p.bronze.*)
# MAGIC stale_bronze = sorted(set(re.findall(r"automation_[dap]\.bronze\.\w+", ser_text)))
# MAGIC
# MAGIC datasets = ser.get("datasets", []) if isinstance(ser, dict) else []
# MAGIC bad_cat = sorted({d.get("catalog") for d in datasets} - {UNITY_CATALOG, None})
# MAGIC bad_sch = sorted({d.get("schema") for d in datasets} - {"silver", None})
# MAGIC
# MAGIC print(f"display_name   : {display_name}")
# MAGIC print(f"lifecycle_state: {lifecycle_state}")
# MAGIC print(f"datasets       : {len(datasets)}")
# MAGIC print(f"stale genie refs : {stale_genie or 'none'}")
# MAGIC print(f"stale bronze refs: {stale_bronze or 'none'}")
# MAGIC print(f"bad catalogs     : {bad_cat or 'none'}")
# MAGIC print(f"bad schemas      : {bad_sch or 'none'}")
# MAGIC
# MAGIC if stale_genie or stale_bronze or bad_cat or bad_sch:
# MAGIC     raise Exception(
# MAGIC         "Publish blocked: dashboard still references wrong catalog/schema. "
# MAGIC         f"genie={stale_genie} bronze={stale_bronze} cat={bad_cat} sch={bad_sch}"
# MAGIC     )
# MAGIC print("Pre-publish check PASSED")

# COMMAND ----------

# DBTITLE 1,Publish Lakeview Dashboard
# MAGIC %python
# MAGIC if hasattr(w.lakeview, "publish"):
# MAGIC     published = w.lakeview.publish(
# MAGIC         dashboard_id=DASHBOARD_ID,
# MAGIC         warehouse_id=WAREHOUSE_ID,
# MAGIC     )
# MAGIC     print(f"Published via SDK: {published}")
# MAGIC else:
# MAGIC     published = w.api_client.do(
# MAGIC         "POST",
# MAGIC         f"/api/2.0/lakeview/dashboards/{DASHBOARD_ID}/published",
# MAGIC         body={"warehouse_id": WAREHOUSE_ID},
# MAGIC     )
# MAGIC     print(f"Published via REST: {published}")

# COMMAND ----------

# DBTITLE 1,Confirm Published Revision
# MAGIC %python
# MAGIC if hasattr(w.lakeview, "get_published"):
# MAGIC     pub = w.lakeview.get_published(DASHBOARD_ID)
# MAGIC     print("published revision OK")
# MAGIC     for attr in ("warehouse_id", "embed_credentials", "revision_create_time", "lifecycle_state"):
# MAGIC         if hasattr(pub, attr):
# MAGIC             print(f"  {attr}: {getattr(pub, attr)}")
# MAGIC else:
# MAGIC     pub = w.api_client.do(
# MAGIC         "GET",
# MAGIC         f"/api/2.0/lakeview/dashboards/{DASHBOARD_ID}/published",
# MAGIC     )
# MAGIC     print(f"published revision OK: {pub}")
# MAGIC
# MAGIC dbutils.notebook.exit("PUBLISHED")
