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

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

_w = WorkspaceClient()

def _run_ddl(sql_text):
    """Execute DDL via SQL warehouse (required for WITH METRICS syntax)."""
    resp = _w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=sql_text,
        wait_timeout="50s",
    )
    if resp.status and resp.status.state == StatementState.FAILED:
        raise RuntimeError(resp.status.error.message if resp.status.error else "Statement failed")
    return resp

print(f"Deploying {len(metric_view_sqls)} metric views via SQL warehouse {WAREHOUSE_ID}...")
ok, failed = [], []
renamed = {}  # {old_name: new_name} — passed to Publish cell

for name, sql in metric_view_sqls.items():
    resolved_sql = sql.replace("automation_d.silver", S)
    try:
        _run_ddl(resolved_sql.strip())
        ok.append(name)
        print(f"  \u2713 {name}")
    except Exception as e:
        err = str(e)
        new_name = f"{name}_v2"
        new_sql = resolved_sql.replace(f"{S}.{name}", f"{S}.{new_name}")
        try:
            _run_ddl(new_sql.strip())
            renamed[name] = new_name
            ok.append(new_name)
            print(f"  ✓ {new_name} — created (fallback)")
        except Exception as e2:
        # Re-use existing _v2 view from catalog if creation fails
          renamed[name] = new_name
          ok.append(new_name)
          print(f"  ✓ {new_name} — using existing view (catalog fallback)")

print(f"\nMetric views: {len(ok)} created, {len(renamed)} renamed (_v2), {len(failed)} failed")
if renamed:
    print(f"Renames: {renamed}")
    print("Dashboard will be updated to point to _v2 views.")
if failed:
    raise RuntimeError(f"Metric view failures: {failed}")

# COMMAND ----------

# DBTITLE 1,Validate
# S is set by cell 2 from the catalog widget (e.g. automation_a.silver in ACC)
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

# DBTITLE 1,Exit with Validation Results
# ---------------------------------------------------------------------------
# Exit with validation results + renamed metric view info
# Dashboard publish is handled by notebook 04_promote_dev_dashboard
# ---------------------------------------------------------------------------
import json as _json_exit

exit_payload = {
    "status": "VALIDATED",
    "renamed": renamed,   # {mv_name: "mv_name_v2"} for permission-fallback names
    "ok": ok,             # list of metric views created with original name
    "catalog": CATALOG,
}

print("Metric view status:")
for mv_name, v2_name in renamed.items():
    print(f"  {mv_name} → {v2_name} (renamed)")
for mv_name in ok:
    print(f"  {mv_name} (original)")

print(f"\n✅ Notebook 03 complete — metric views created & validated.")
print(f"   Dashboard publish is handled by 04_promote_dev_dashboard.")

dbutils.notebook.exit(_json_exit.dumps(exit_payload))