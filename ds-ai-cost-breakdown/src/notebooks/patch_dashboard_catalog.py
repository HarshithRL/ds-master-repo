# Databricks notebook source
# Patch the deployed AI Cost Dashboard to point at this environment's catalog, then publish.
# The .lvdash.json in git is authored against DEV (automation_d.gold); this swaps it per target.
# Same pattern as copilot-dashboard/src/04_promote_dev_dashboard.py, reduced to the catalog swap.

# COMMAND ----------

import json
from databricks.sdk import WorkspaceClient

dbutils.widgets.text("catalog", "automation_d")
dbutils.widgets.text("dashboard_id", "")
dbutils.widgets.text("warehouse_id", "")

CATALOG = dbutils.widgets.get("catalog").strip()
DASHBOARD_ID = dbutils.widgets.get("dashboard_id").strip()
WAREHOUSE_ID = dbutils.widgets.get("warehouse_id").strip()
SOURCE_CATALOG = "automation_d"

assert DASHBOARD_ID, "dashboard_id is empty"
assert WAREHOUSE_ID, "warehouse_id is empty"

w = WorkspaceClient()
api = w.api_client  # raw REST: avoids lakeview SDK signature changes across runtime versions

# COMMAND ----------

dash = api.do("GET", f"/api/2.0/lakeview/dashboards/{DASHBOARD_ID}")
ser = dash["serialized_dashboard"]

patched = ser
if CATALOG != SOURCE_CATALOG:
    patched = patched.replace(f'"{SOURCE_CATALOG}"', f'"{CATALOG}"')          # dataset "catalog" fields
    patched = patched.replace(f"{SOURCE_CATALOG}.gold.", f"{CATALOG}.gold.")  # SQL sources

# Sanity: no DEV references left outside DEV
if CATALOG != SOURCE_CATALOG:
    assert SOURCE_CATALOG not in patched, f"{SOURCE_CATALOG} still referenced after patch"
json.loads(patched)  # still valid JSON

if patched != ser:
    api.do("PATCH", f"/api/2.0/lakeview/dashboards/{DASHBOARD_ID}",
           body={"serialized_dashboard": patched, "etag": dash.get("etag")})
    print(f"Patched {SOURCE_CATALOG} -> {CATALOG}")
else:
    print("No catalog change needed")

# COMMAND ----------

api.do("POST", f"/api/2.0/lakeview/dashboards/{DASHBOARD_ID}/published",
       body={"warehouse_id": WAREHOUSE_ID, "embed_credentials": True})
print(f"Published dashboard {DASHBOARD_ID} on warehouse {WAREHOUSE_ID}")