# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,03 - Metrics, Validate & Publish
# MAGIC %md
# MAGIC # 03 - Metrics, Validate & Publish
# MAGIC
# MAGIC **Purpose:** Creates all 6 metric views, validates the data, and publishes the dashboard.
# MAGIC
# MAGIC **Run after:** `02_silver_dimensional`
# MAGIC
# MAGIC **Metric views:** `bot_usage_metrics`, `copilot_analytics_metrics`, `metric_agent_governance`, `metric_credit_consumption`, `metric_agent_feature_credit`, `metric_environment_consumption`

# COMMAND ----------

# DBTITLE 1,Config
import json as _json, os

dbutils.widgets.text("catalog", "automation_d", "Catalog")
dbutils.widgets.text("warehouse_id", "69ada62b2fb9b9e2", "Warehouse ID")

CATALOG = dbutils.widgets.get("catalog")
WAREHOUSE_ID = dbutils.widgets.get("warehouse_id")

S = f"{CATALOG}.silver"
VOLUME_BASE = f"/Volumes/{CATALOG}/bronze/bronze_volume/Copilot_Dashboard_Data"
CONFIG_FILE = f"{VOLUME_BASE}/_pipeline_config.json"
TEMPLATE_FILE = f"{VOLUME_BASE}/_dashboard_template.json"

# Read dashboard ID from persistent config (survives dashboard recreation)
# If no config exists, DASHBOARD_ID stays None → Publish cell will create from template
try:
    with open(CONFIG_FILE) as f:
        _cfg = _json.load(f)
    DASHBOARD_ID = _cfg.get("dashboard_id")
    if DASHBOARD_ID:
        print(f"Dashboard ID from config: {DASHBOARD_ID}")
    else:
        print("Config exists but no dashboard_id — will create from template.")
except FileNotFoundError:
    DASHBOARD_ID = None
    print("No pipeline config found — dashboard will be created from template on first run.")

print(f"Schema: {S}")

# COMMAND ----------

# DBTITLE 1,Create or Refresh Metric Views
# Run all 6 metric view definitions. If we lack MANAGE permission (owned by
# another user), the view already exists with the correct definition — skip it.

metric_view_sqls = {}

metric_view_sqls["bot_usage_metrics"] = """
CREATE OR REPLACE VIEW automation_d.silver.bot_usage_metrics
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Bot usage & adoption KPIs."
source: |
  SELECT b.bot_name, b.usage_date, b.environment, b.conversations, r.max_dt, r.current_month
  FROM automation_d.silver.bot_usage AS b
  CROSS JOIN (SELECT MAX(usage_date) AS max_dt, DATE_TRUNC('MONTH', MAX(usage_date)) AS current_month FROM automation_d.silver.bot_usage) AS r
dimensions:
  - name: Bot Name
    expr: source.bot_name
  - name: Environment
    expr: source.environment
  - name: Environment Type
    expr: CASE WHEN source.environment LIKE '%PROD%' THEN 'Production' WHEN LOWER(source.environment) LIKE '%default%' THEN 'Default environment' ELSE 'Dev / Test / Other' END
  - name: Usage Date
    expr: source.usage_date
  - name: Usage Month
    expr: DATE_TRUNC('MONTH', source.usage_date)
  - name: Usage Quarter
    expr: DATE_TRUNC('QUARTER', source.usage_date)
  - name: Usage Month Label
    expr: DATE_FORMAT(DATE_TRUNC('MONTH', source.usage_date), 'MMM yyyy')
  - name: Is Current Partial Month
    expr: CASE WHEN DATE_TRUNC('MONTH', source.usage_date) = source.current_month THEN true ELSE false END
measures:
  - name: total_conversations
    expr: SUM(source.conversations)
  - name: total_agents
    expr: COUNT(DISTINCT source.bot_name)
  - name: total_environments
    expr: COUNT(DISTINCT source.environment)
  - name: active_days
    expr: COUNT(DISTINCT source.usage_date)
  - name: avg_conversations_per_bot_day
    expr: ROUND(AVG(source.conversations), 2)
  - name: active_agents_30d
    expr: COUNT(DISTINCT CASE WHEN source.usage_date >= DATE_SUB(source.max_dt, 30) THEN source.bot_name END)
  - name: active_agents_60d
    expr: COUNT(DISTINCT CASE WHEN source.usage_date >= DATE_SUB(source.max_dt, 60) THEN source.bot_name END)
  - name: pct_active_agents
    expr: ROUND(COUNT(DISTINCT CASE WHEN source.usage_date >= DATE_SUB(source.max_dt, 30) THEN source.bot_name END) * 100.0 / NULLIF(COUNT(DISTINCT source.bot_name), 0), 1)
  - name: first_used
    expr: MIN(source.usage_date)
  - name: last_used
    expr: MAX(source.usage_date)
  - name: days_since_last_use
    expr: DATEDIFF(MAX(source.max_dt), MAX(source.usage_date))
  - name: latest_data_date
    expr: MAX(source.max_dt)
$$;
"""

metric_view_sqls["metric_agent_feature_credit"] = """
CREATE OR REPLACE VIEW automation_d.silver.metric_agent_feature_credit
WITH METRICS LANGUAGE YAML AS $$
version: 0.1
source: automation_d.silver.vw_agent_credit_detail
dimensions:
  - name: product
    expr: product
  - name: agent_category
    expr: agent_category
  - name: ai_feature
    expr: ai_feature
  - name: channel
    expr: channel
  - name: llm_model
    expr: llm_model
  - name: environment_name
    expr: environment_name
measures:
  - name: billed_credits
    expr: SUM(billed_credit)
  - name: non_billed_credits
    expr: SUM(non_billed_credit)
  - name: total_credits
    expr: SUM(total_credit)
  - name: agent_credits
    expr: SUM(CASE WHEN agent_category <> 'Platform Tool' THEN total_credit END)
  - name: total_cost_eur
    expr: SUM(total_credit_cost_eur)
$$;
"""

metric_view_sqls["metric_agent_governance"] = """
CREATE OR REPLACE VIEW automation_d.silver.metric_agent_governance
WITH METRICS LANGUAGE YAML AS $$
version: 0.1
source: automation_d.silver.vw_agent_governance
dimensions:
  - name: platform
    expr: platform
  - name: agent_category
    expr: agent_category
  - name: status
    expr: status
  - name: owner
    expr: owner
  - name: created_by
    expr: created_by
  - name: orchestration
    expr: orchestration
  - name: model
    expr: model
  - name: environment_type
    expr: environment_type
  - name: environment_region
    expr: environment_region
  - name: is_managed
    expr: is_managed
  - name: usage_status
    expr: usage_status
  - name: created_year
    expr: created_year
  - name: created_month
    expr: created_month
measures:
  - name: total_agent_count
    expr: COUNT(DISTINCT agent_key)
  - name: valid_agent_count
    expr: COUNT(DISTINCT CASE WHEN is_valid_agent THEN agent_key END)
  - name: maker_count
    expr: COUNT(DISTINCT CASE WHEN is_valid_agent THEN created_by END)
  - name: no_auth_count
    expr: COUNT(DISTINCT CASE WHEN is_no_auth THEN agent_key END)
  - name: used_agent_count
    expr: COUNT(DISTINCT CASE WHEN is_valid_agent AND is_used THEN agent_key END)
  - name: dormant_agent_count
    expr: COUNT(DISTINCT CASE WHEN is_valid_agent AND NOT is_used THEN agent_key END)
  - name: created_last_30d
    expr: COUNT(DISTINCT CASE WHEN is_valid_agent AND created_on_date > current_date() - 30 AND created_on_date <= current_date() THEN agent_key END)
  - name: published_agent_count
    expr: COUNT(DISTINCT CASE WHEN is_valid_agent AND status = 'Available' THEN agent_key END)
  - name: draft_valid_agent_count
    expr: COUNT(DISTINCT CASE WHEN is_valid_agent AND coalesce(status, '-') <> 'Available' THEN agent_key END)
  - name: unpublished_agent_count
    expr: COUNT(DISTINCT CASE WHEN coalesce(status, '-') <> 'Available' THEN agent_key END)
  - name: unpublished_studio_count
    expr: COUNT(DISTINCT CASE WHEN platform = 'Copilot Studio' AND coalesce(status, '-') <> 'Available' THEN agent_key END)
  - name: orphan_agent_count
    expr: COUNT(DISTINCT CASE WHEN is_valid_agent AND (owner IS NULL OR owner = '-') THEN agent_key END)
  - name: unmanaged_env_agent_count
    expr: COUNT(DISTINCT CASE WHEN is_valid_agent AND NOT is_managed THEN agent_key END)
  - name: at_risk_agent_count
    expr: COUNT(DISTINCT CASE WHEN is_valid_agent AND (is_no_auth OR NOT is_managed OR (owner IS NULL OR owner = '-')) THEN agent_key END)
$$;
"""

metric_view_sqls["metric_credit_consumption"] = """
CREATE OR REPLACE VIEW automation_d.silver.metric_credit_consumption
WITH METRICS LANGUAGE YAML AS $$
version: 0.1
source: automation_d.silver.vw_user_agent_usage
dimensions:
  - name: user_email
    expr: user_email
  - name: m365_copilot_licensed
    expr: m365_copilot_licensed
  - name: agent_name
    expr: agent_name
  - name: agent_category
    expr: agent_category
  - name: platform
    expr: platform
measures:
  - name: total_consumption_credits
    expr: SUM(credits_used)
  - name: total_spend_credits
    expr: SUM(billable_credit_used)
  - name: absorbed_credits
    expr: SUM(credits_used - billable_credit_used)
  - name: agent_consumption_credits
    expr: SUM(CASE WHEN agent_category <> 'Platform Tool' THEN credits_used END)
  - name: platform_consumption_credits
    expr: SUM(CASE WHEN agent_category = 'Platform Tool' THEN credits_used END)
  - name: total_consumption_cost_eur
    expr: SUM(consumption_cost_eur)
  - name: active_users
    expr: COUNT(DISTINCT user_key)
  - name: agents_used
    expr: COUNT(DISTINCT credit_agent_id)
$$;
"""

metric_view_sqls["metric_environment_consumption"] = """
CREATE OR REPLACE VIEW automation_d.silver.metric_environment_consumption
WITH METRICS LANGUAGE YAML AS $$
version: 0.1
source: automation_d.silver.vw_environment_daily
dimensions:
  - name: environment_name
    expr: environment_name
  - name: environment_type
    expr: environment_type
  - name: environment_region
    expr: environment_region
  - name: year
    expr: year
  - name: month
    expr: month
  - name: month_name
    expr: month_name
  - name: date_eu
    expr: date_eu
  - name: date
    expr: date
measures:
  - name: prepaid_consumed_credits
    expr: SUM(prepaid_consumed_quantity)
  - name: pay_as_you_go_credits
    expr: SUM(pay_as_you_go_consumed_quantity)
  - name: entitled_credits
    expr: SUM(entitled_quantity)
  - name: prepaid_consumed_cost_eur
    expr: SUM(prepaid_cost_eur)
  - name: active_days
    expr: COUNT(DISTINCT date)
$$;
"""

metric_view_sqls["copilot_analytics_metrics"] = """
CREATE OR REPLACE VIEW automation_d.silver.copilot_analytics_metrics
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: automation_d.silver.silver_fact_interactions
comment: Etex M365 Copilot - interaction KPIs.

joins:
  - name: dim_env
    source: automation_d.silver.silver_dim_environment
    on: source.env_id = dim_env.environment_id
    cardinality: many_to_one
    rely:
      at_most_one_match: true

dimensions:
  - name: Interaction Type
    expr: interaction_type
  - name: License Type
    expr: license_type
  - name: Uses Bing Search
    expr: uses_bing_search
  - name: Model Provider
    expr: model_provider
  - name: Region
    expr: admin_unit_name
  - name: Interaction Date
    expr: creation_date
  - name: User Email
    expr: user_email
  - name: Agent Name
    expr: agent_name
  - name: Target Agent ID
    expr: target_agent_id
  - name: Environment ID
    expr: env_id
  - name: Environment Name
    expr: dim_env.environment_name
  - name: App Host
    expr: app_host

measures:
  - name: Total Interactions
    expr: COUNT(1)
  - name: Unique Active Users
    expr: COUNT(DISTINCT user_email)
  - name: Avg Interactions per User
    expr: MEASURE(`Total Interactions`) / MEASURE(`Unique Active Users`)
  - name: Bing Interactions
    expr: COUNT(1) FILTER (WHERE uses_bing_search = TRUE)
  - name: Pct Using Bing
    expr: MEASURE(`Bing Interactions`) * 100.0 / MEASURE(`Total Interactions`)
  - name: OpenAI Interactions
    expr: COUNT(1) FILTER (WHERE model_provider = 'OpenAI')
  - name: Premium Interactions
    expr: COUNT(1) FILTER (WHERE license_type = 'Premium')
  - name: Starter Interactions
    expr: COUNT(1) FILTER (WHERE license_type = 'Starter')
  - name: Premium Share
    expr: MEASURE(`Premium Interactions`) * 100.0 / MEASURE(`Total Interactions`)
  - name: Declarative Interactions
    expr: COUNT(1) FILTER (WHERE interaction_type = 'Declarative')
  - name: Custom Engine Interactions
    expr: COUNT(1) FILTER (WHERE interaction_type = 'CustomEngine')
  - name: BizChat M365 Interactions
    expr: COUNT(1) FILTER (WHERE interaction_type = 'BizChat_M365')
  - name: Unique Environments
    expr: COUNT(DISTINCT env_id) FILTER (WHERE env_id IS NOT NULL AND env_id != '')
  - name: Unique Regions
    expr: COUNT(DISTINCT admin_unit_name) FILTER (WHERE admin_unit_name IS NOT NULL)
  - name: Interactions by Region
    expr: COUNT(1) FILTER (WHERE admin_unit_name IS NOT NULL)
  - name: Active Users by Region
    expr: COUNT(DISTINCT user_email) FILTER (WHERE admin_unit_name IS NOT NULL)
  - name: Avg Interactions per User by Region
    expr: MEASURE(`Interactions by Region`) / MEASURE(`Active Users by Region`)
$$;
"""

print(f"Deploying {len(metric_view_sqls)} metric views...")
ok, failed = [], []
renamed = {}  # {old_name: new_name} — passed to Publish cell

for name, sql in metric_view_sqls.items():
    resolved_sql = sql.replace("automation_d.silver", S)
    try:
        spark.sql(resolved_sql.strip())
        ok.append(name)
        print(f"  \u2713 {name}")
    except Exception as e:
        err = str(e)
        if "UNAUTHORIZED" in err or "PERMISSION_DENIED" in err or "MANAGE" in err:
            # Can't replace (owned by another user) — create with _v2 suffix
            new_name = f"{name}_v2"
            new_sql = resolved_sql.replace(f"{S}.{name}", f"{S}.{new_name}")
            try:
                spark.sql(new_sql.strip())
                renamed[name] = new_name
                ok.append(new_name)
                print(f"  \u2713 {new_name} \u2014 created (no MANAGE on original '{name}')")
            except Exception as e2:
                failed.append(name)
                print(f"  \u2717 {name} \u2014 can't replace or create _v2: {e2}")
        else:
            failed.append(name)
            print(f"  \u2717 {name} \u2014 {err[:120]}")

print(f"\nMetric views: {len(ok)} created, {len(renamed)} renamed (_v2), {len(failed)} failed")
if renamed:
    print(f"Renames: {renamed}")
    print("Dashboard will be updated to point to _v2 views.")
if failed:
    raise RuntimeError(f"Metric view failures: {failed}")

# COMMAND ----------

# DBTITLE 1,Validate
S = "automation_d.silver"
failures = []

# Smoke counts
smoke_objects = ["dim_agent", "fact_agent_credit", "bot_usage", "sl_purview_log", "silver_fact_interactions"]
print("=== Smoke counts ===")
for obj in smoke_objects:
    fq = f"{S}.{obj}"
    try:
        n = spark.table(fq).count()
        print(f"  {fq}: {n:,} rows")
        if n == 0 and obj not in ("sl_purview_log", "silver_fact_interactions"):
            failures.append(f"smoke: {fq} has 0 rows")
    except Exception as e:
        failures.append(f"smoke: {fq} missing/error: {e}")
        print(f"  FAIL {fq}: {e}")

# Metric views (use _v2 names if they were renamed due to permission issues)
metric_views = ["bot_usage_metrics", "copilot_analytics_metrics", "metric_agent_governance",
                "metric_credit_consumption", "metric_agent_feature_credit", "metric_environment_consumption"]
print("=== Metric views ===")
for mv in metric_views:
    actual_name = renamed.get(mv, mv)  # use _v2 name if renamed
    fq = f"{S}.{actual_name}"
    try:
        spark.sql(f"DESCRIBE TABLE {fq}").collect()
        suffix = " (renamed)" if actual_name != mv else ""
        print(f"  OK {fq}{suffix}")
    except Exception as e:
        failures.append(f"metric_view: {fq} missing: {e}")
        print(f"  FAIL {fq}: {e}")

print("=" * 60)
if failures:
    print(f"VALIDATE FAILED ({len(failures)} issue(s))")
    for f in failures:
        print(f"  - {f}")
    raise Exception(f"Validate failed: {len(failures)} issue(s)")
else:
    print("VALIDATE PASSED - safe to publish")

# COMMAND ----------

# DBTITLE 1,Publish Dashboard
import json
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Resolve pipeline folder dynamically (same folder as this notebook)
import os as _os
PIPELINE_FOLDER = _os.path.dirname(dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get())

# ---------------------------------------------------------------------------
# 1. Ensure dashboard exists — create from template if missing
# ---------------------------------------------------------------------------
def _save_config(dashboard_id):
    """Persist current dashboard ID so future runs find it."""
    cfg = {"dashboard_id": dashboard_id}
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"  Config saved: {CONFIG_FILE}")


def _get_or_create_dashboard():
    """Return (dashboard_id, serialized_dashboard_json, display_name)."""
    global DASHBOARD_ID

    # Try to read the existing dashboard (skip if no ID)
    if DASHBOARD_ID:
        try:
            draft = w.lakeview.get(DASHBOARD_ID)
            # Check lifecycle state — TRASHED dashboards can't be published
            state = getattr(draft, 'lifecycle_state', None)
            state_val = getattr(state, 'value', str(state)).upper() if state else ''
            if 'TRASHED' in state_val:
                print(f"Dashboard {DASHBOARD_ID} is TRASHED. Creating fresh from template...")
            else:
                ser = draft.serialized_dashboard
                name = draft.display_name
                print(f"Dashboard found: {name} ({DASHBOARD_ID})")
                return DASHBOARD_ID, ser, name
        except Exception as e:
            err_str = str(e).upper()
            if not any(k in err_str for k in ["NOT_FOUND", "NOTFOUND", "404", "RESOURCE_DOES_NOT_EXIST", "TRASHED"]):
                raise
            print(f"Dashboard {DASHBOARD_ID} unavailable ({type(e).__name__}). Creating from template...")
    else:
        print("No dashboard ID configured. Creating from template...")

    # Load template and adapt to current catalog
    with open(TEMPLATE_FILE) as f:
        tmpl = json.load(f)
    ser = tmpl["serialized_dashboard"]
    name = tmpl.get("display_name", "Agent Dashboard Phase 1")

    # Template was saved from automation_d — replace with current catalog
    if CATALOG != "automation_d":
        ser = ser.replace("automation_d.silver", f"{CATALOG}.silver")
        ser = ser.replace("automation_d.bronze", f"{CATALOG}.bronze")
        print(f"  Template adapted: automation_d -> {CATALOG}")

    # Create new dashboard in the pipeline folder (REST API for compatibility)
    resp = w.api_client.do("POST", "/api/2.0/lakeview/dashboards", body={
        "display_name": name,
        "serialized_dashboard": ser,
        "warehouse_id": WAREHOUSE_ID,
        "parent_path": PIPELINE_FOLDER,
    })
    new_id = resp.get("dashboard_id") if isinstance(resp, dict) else getattr(resp, "dashboard_id", None)
    if not new_id:
        raise RuntimeError(f"Dashboard creation returned no ID: {resp}")
    print(f"  Created new dashboard: {name} ({new_id})")

    # Persist the new ID
    DASHBOARD_ID = new_id
    _save_config(new_id)

    # Also update the template with the new default
    return new_id, ser, name


dash_id, ser_raw, display_name = _get_or_create_dashboard()

# ---------------------------------------------------------------------------
# 2. Sync dashboard JSON with metric view names
#    - renamed has _v2 entries     → old -> _v2 in dashboard
#    - ok has originals (no rename) → _v2 -> old in dashboard (revert)
# ---------------------------------------------------------------------------
updated_json = ser_raw
changes_made = 0

ALL_METRIC_VIEWS = ["bot_usage_metrics", "copilot_analytics_metrics", "metric_agent_governance",
                    "metric_credit_consumption", "metric_agent_feature_credit", "metric_environment_consumption"]

for mv in ALL_METRIC_VIEWS:
    v2_ref = f"{S}.{mv}_v2"
    orig_ref = f"{S}.{mv}"

    if mv in renamed:
        # We created _v2 this run — dashboard should point to _v2
        if orig_ref in updated_json and v2_ref not in updated_json:
            updated_json = updated_json.replace(orig_ref, v2_ref)
            print(f"  {orig_ref} -> {v2_ref}")
            changes_made += 1
    else:
        # Original succeeded this run — revert any leftover _v2 references
        if v2_ref in updated_json:
            updated_json = updated_json.replace(v2_ref, orig_ref)
            print(f"  {v2_ref} -> {orig_ref} (reverted to original)")
            changes_made += 1

if changes_made > 0:
    w.lakeview.update(dashboard_id=dash_id, serialized_dashboard=updated_json)
    print(f"  Dashboard updated ({changes_made} reference(s) changed).")

    # Also update the template so future auto-creates use current names
    try:
        with open(TEMPLATE_FILE) as f:
            tmpl = json.load(f)
        tmpl["serialized_dashboard"] = updated_json
        with open(TEMPLATE_FILE, "w") as f:
            json.dump(tmpl, f, indent=2)
        print(f"  Template also updated.")
    except Exception:
        pass  # non-critical
else:
    print("  Dashboard references already correct.")

# ---------------------------------------------------------------------------
# 3. Publish
# ---------------------------------------------------------------------------
print(f"\nPublishing {display_name}...")
w.lakeview.publish(dashboard_id=dash_id, warehouse_id=WAREHOUSE_ID, embed_credentials=True)

# Confirm
w.lakeview.get_published(dash_id)
print(f"Published OK.")

dbutils.notebook.exit(json.dumps({"status": "PUBLISHED", "dashboard_id": dash_id}))
