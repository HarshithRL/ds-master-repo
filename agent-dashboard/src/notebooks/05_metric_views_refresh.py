# Databricks notebook source
# MAGIC %run ./config_file

# COMMAND ----------

# MAGIC %python
# MAGIC spark.sql(f"USE CATALOG {UNITY_CATALOG}")
# MAGIC print(f"Active catalog: {UNITY_CATALOG}")

# COMMAND ----------
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Metric Views Refresh - Introduction
# MAGIC %md
# MAGIC # Metric Views Refresh
# MAGIC
# MAGIC **Purpose:** Create/refresh all metric views in `{SILVER}` so the dashboard reads the latest pipeline data.
# MAGIC
# MAGIC **When to run:** After new files are uploaded to the volume and the pipeline (Etex Excel to bronze + Etex Silver Layer Pipeline) completes.
# MAGIC
# MAGIC **Metric Views:**
# MAGIC 1. `metric_agent_feature_credit` — Credit breakdown by product/feature/channel/model
# MAGIC 2. `metric_agent_governance` — Governance KPIs over agent inventory
# MAGIC 3. `metric_credit_consumption` — Credit by user x agent
# MAGIC 4. `metric_environment_consumption` — Daily environment MCS-message consumption
# MAGIC 5. `copilot_analytics_metrics` — Copilot interaction KPIs (already in Metric Creation notebook)
# MAGIC 6. `bot_usage_metrics` — Bot usage & adoption (already in Bot_Usage_Metrics notebook)

# COMMAND ----------

# DBTITLE 1,Metric View 1 - Agent Feature Credit
# MAGIC %sql
# MAGIC CREATE OR REPLACE VIEW silver.metric_agent_feature_credit (
# MAGIC   product,
# MAGIC   agent_category,
# MAGIC   ai_feature,
# MAGIC   channel,
# MAGIC   llm_model,
# MAGIC   environment_name,
# MAGIC   billed_credits,
# MAGIC   non_billed_credits,
# MAGIC   total_credits,
# MAGIC   agent_credits,
# MAGIC   total_cost_eur)
# MAGIC COMMENT 'Credit breakdown by product/feature/channel/model (sl_agent_credit world). agent_category: Platform Tool (= Dataverse MCP tool/server, ~98% of credit here, NOT an agent) vs Copilot Studio. Use for the product split; do NOT combine with metric_credit_consumption splits (the two facts split the same 3309.9 pool inversely).'
# MAGIC WITH METRICS
# MAGIC LANGUAGE YAML
# MAGIC AS
# MAGIC $$
# MAGIC
# MAGIC version: 0.1
# MAGIC source: silver.vw_agent_credit_detail
# MAGIC dimensions:
# MAGIC   - name: product
# MAGIC     expr: product
# MAGIC   - name: agent_category
# MAGIC     expr: agent_category
# MAGIC   - name: ai_feature
# MAGIC     expr: ai_feature
# MAGIC   - name: channel
# MAGIC     expr: channel
# MAGIC   - name: llm_model
# MAGIC     expr: llm_model
# MAGIC   - name: environment_name
# MAGIC     expr: environment_name
# MAGIC measures:
# MAGIC   - name: billed_credits
# MAGIC     expr: SUM(billed_credit)
# MAGIC   - name: non_billed_credits
# MAGIC     expr: SUM(non_billed_credit)
# MAGIC   - name: total_credits
# MAGIC     expr: SUM(total_credit)
# MAGIC   - name: agent_credits
# MAGIC     expr: SUM(CASE WHEN agent_category <> 'Platform Tool' THEN total_credit END)
# MAGIC   - name: total_cost_eur
# MAGIC     expr: SUM(total_credit_cost_eur)
# MAGIC $$;

# COMMAND ----------

# DBTITLE 1,Metric View 2 - Agent Governance
# MAGIC %sql
# MAGIC CREATE OR REPLACE VIEW silver.metric_agent_governance (
# MAGIC   platform,
# MAGIC   agent_category,
# MAGIC   status,
# MAGIC   owner,
# MAGIC   created_by,
# MAGIC   orchestration,
# MAGIC   model,
# MAGIC   environment_type,
# MAGIC   environment_region,
# MAGIC   is_managed,
# MAGIC   usage_status,
# MAGIC   created_year,
# MAGIC   created_month,
# MAGIC   total_agent_count,
# MAGIC   valid_agent_count,
# MAGIC   maker_count,
# MAGIC   no_auth_count,
# MAGIC   used_agent_count,
# MAGIC   dormant_agent_count,
# MAGIC   created_last_30d,
# MAGIC   published_agent_count,
# MAGIC   draft_valid_agent_count,
# MAGIC   unpublished_agent_count,
# MAGIC   unpublished_studio_count,
# MAGIC   orphan_agent_count,
# MAGIC   unmanaged_env_agent_count,
# MAGIC   at_risk_agent_count)
# MAGIC COMMENT 'Governance KPIs over agent inventory. Valid-agent filter is applied inside the measures (flag lives in Gold).'
# MAGIC WITH METRICS
# MAGIC LANGUAGE YAML
# MAGIC AS
# MAGIC $$
# MAGIC
# MAGIC version: 0.1
# MAGIC source: silver.vw_agent_governance
# MAGIC dimensions:
# MAGIC   - name: platform
# MAGIC     expr: platform
# MAGIC   - name: agent_category
# MAGIC     expr: agent_category
# MAGIC   - name: status
# MAGIC     expr: status
# MAGIC   - name: owner
# MAGIC     expr: owner
# MAGIC   - name: created_by
# MAGIC     expr: created_by
# MAGIC   - name: orchestration
# MAGIC     expr: orchestration
# MAGIC   - name: model
# MAGIC     expr: model
# MAGIC   - name: environment_type
# MAGIC     expr: environment_type
# MAGIC   - name: environment_region
# MAGIC     expr: environment_region
# MAGIC   - name: is_managed
# MAGIC     expr: is_managed
# MAGIC   - name: usage_status
# MAGIC     expr: usage_status
# MAGIC   - name: created_year
# MAGIC     expr: created_year
# MAGIC   - name: created_month
# MAGIC     expr: created_month
# MAGIC measures:
# MAGIC   - name: total_agent_count
# MAGIC     expr: COUNT(DISTINCT agent_key)
# MAGIC   - name: valid_agent_count
# MAGIC     expr: COUNT(DISTINCT CASE WHEN is_valid_agent THEN agent_key END)
# MAGIC   - name: maker_count
# MAGIC     expr: COUNT(DISTINCT CASE WHEN is_valid_agent THEN created_by END)
# MAGIC   - name: no_auth_count
# MAGIC     expr: COUNT(DISTINCT CASE WHEN is_no_auth THEN agent_key END)
# MAGIC   - name: used_agent_count
# MAGIC     expr: COUNT(DISTINCT CASE WHEN is_valid_agent AND is_used THEN agent_key END)
# MAGIC   - name: dormant_agent_count
# MAGIC     expr: COUNT(DISTINCT CASE WHEN is_valid_agent AND NOT is_used THEN agent_key END)
# MAGIC   - name: created_last_30d
# MAGIC     expr: COUNT(DISTINCT CASE WHEN is_valid_agent AND created_on_date > current_date() - 30 AND created_on_date <= current_date() THEN agent_key END)
# MAGIC   - name: published_agent_count
# MAGIC     expr: COUNT(DISTINCT CASE WHEN is_valid_agent AND status = 'Available' THEN agent_key END)
# MAGIC   - name: draft_valid_agent_count
# MAGIC     expr: COUNT(DISTINCT CASE WHEN is_valid_agent AND coalesce(status, '-') <> 'Available' THEN agent_key END)
# MAGIC   - name: unpublished_agent_count
# MAGIC     expr: COUNT(DISTINCT CASE WHEN coalesce(status, '-') <> 'Available' THEN agent_key END)
# MAGIC   - name: unpublished_studio_count
# MAGIC     expr: COUNT(DISTINCT CASE WHEN platform = 'Copilot Studio' AND is_valid_agent AND coalesce(status, '-') <> 'Available' THEN agent_key END)
# MAGIC   - name: orphan_agent_count
# MAGIC     expr: COUNT(DISTINCT CASE WHEN NOT is_valid_agent THEN agent_key END)
# MAGIC   - name: unmanaged_env_agent_count
# MAGIC     expr: COUNT(DISTINCT CASE WHEN is_valid_agent AND NOT is_managed THEN agent_key END)
# MAGIC   - name: at_risk_agent_count
# MAGIC     expr: COUNT(DISTINCT CASE WHEN is_no_auth OR (NOT is_valid_agent) OR (is_valid_agent AND NOT is_managed) THEN agent_key END)
# MAGIC $$;

# COMMAND ----------

# DBTITLE 1,Metric View 3 - Credit Consumption
# MAGIC %sql
# MAGIC CREATE OR REPLACE VIEW silver.metric_credit_consumption (
# MAGIC   user_email,
# MAGIC   m365_copilot_licensed,
# MAGIC   agent_name,
# MAGIC   agent_category,
# MAGIC   platform,
# MAGIC   total_consumption_credits,
# MAGIC   total_spend_credits,
# MAGIC   absorbed_credits,
# MAGIC   agent_consumption_credits,
# MAGIC   platform_consumption_credits,
# MAGIC   total_consumption_cost_eur,
# MAGIC   active_users,
# MAGIC   agents_used)
# MAGIC COMMENT 'Credit by user x agent (sl_user_credit world). Headline consumption = total_consumption_credits (3309.9). agent_category buckets credit: Copilot Studio / Platform Tool (= Dataverse MCP tool/server, NOT an agent) / Agent Builder (~0, license-absorbed). Filter agent_category <> Platform Tool for true top-agents.'
# MAGIC WITH METRICS
# MAGIC LANGUAGE YAML
# MAGIC AS
# MAGIC $$
# MAGIC
# MAGIC version: 0.1
# MAGIC source: silver.vw_user_agent_usage
# MAGIC dimensions:
# MAGIC   - name: user_email
# MAGIC     expr: user_email
# MAGIC   - name: m365_copilot_licensed
# MAGIC     expr: m365_copilot_licensed
# MAGIC   - name: agent_name
# MAGIC     expr: agent_name
# MAGIC   - name: agent_category
# MAGIC     expr: agent_category
# MAGIC   - name: platform
# MAGIC     expr: platform
# MAGIC measures:
# MAGIC   - name: total_consumption_credits
# MAGIC     expr: SUM(credits_used)
# MAGIC   - name: total_spend_credits
# MAGIC     expr: SUM(billable_credit_used)
# MAGIC   - name: absorbed_credits
# MAGIC     expr: SUM(credits_used - billable_credit_used)
# MAGIC   - name: agent_consumption_credits
# MAGIC     expr: SUM(CASE WHEN agent_category <> 'Platform Tool' THEN credits_used END)
# MAGIC   - name: platform_consumption_credits
# MAGIC     expr: SUM(CASE WHEN agent_category = 'Platform Tool' THEN credits_used END)
# MAGIC   - name: total_consumption_cost_eur
# MAGIC     expr: SUM(consumption_cost_eur)
# MAGIC   - name: active_users
# MAGIC     expr: COUNT(DISTINCT user_key)
# MAGIC   - name: agents_used
# MAGIC     expr: COUNT(DISTINCT credit_agent_id)
# MAGIC $$;

# COMMAND ----------

# DBTITLE 1,Metric View 4 - Environment Consumption
# MAGIC %sql
# MAGIC CREATE OR REPLACE VIEW silver.metric_environment_consumption (
# MAGIC   environment_name,
# MAGIC   environment_type,
# MAGIC   environment_region,
# MAGIC   year,
# MAGIC   month,
# MAGIC   month_name,
# MAGIC   date_eu,
# MAGIC   date,
# MAGIC   prepaid_consumed_credits,
# MAGIC   pay_as_you_go_credits,
# MAGIC   entitled_credits,
# MAGIC   prepaid_consumed_cost_eur,
# MAGIC   active_days)
# MAGIC COMMENT 'Daily environment MCS-message consumption. Contiguous 29 Apr -> 27 May 2026.'
# MAGIC WITH METRICS
# MAGIC LANGUAGE YAML
# MAGIC AS
# MAGIC $$
# MAGIC
# MAGIC version: 0.1
# MAGIC source: silver.vw_environment_daily
# MAGIC dimensions:
# MAGIC   - name: environment_name
# MAGIC     expr: environment_name
# MAGIC   - name: environment_type
# MAGIC     expr: environment_type
# MAGIC   - name: environment_region
# MAGIC     expr: environment_region
# MAGIC   - name: year
# MAGIC     expr: year
# MAGIC   - name: month
# MAGIC     expr: month
# MAGIC   - name: month_name
# MAGIC     expr: month_name
# MAGIC   - name: date_eu
# MAGIC     expr: date_eu
# MAGIC   - name: date
# MAGIC     expr: date
# MAGIC measures:
# MAGIC   - name: prepaid_consumed_credits
# MAGIC     expr: SUM(prepaid_consumed_quantity)
# MAGIC   - name: pay_as_you_go_credits
# MAGIC     expr: SUM(pay_as_you_go_consumed_quantity)
# MAGIC   - name: entitled_credits
# MAGIC     expr: SUM(entitled_quantity)
# MAGIC   - name: prepaid_consumed_cost_eur
# MAGIC     expr: SUM(prepaid_cost_eur)
# MAGIC   - name: active_days
# MAGIC     expr: COUNT(DISTINCT date)
# MAGIC $$;

# COMMAND ----------

# DBTITLE 1,Verification - List all metric views
# MAGIC %python
# MAGIC spark.sql(f"USE CATALOG {UNITY_CATALOG}")
# MAGIC display(spark.sql("SHOW VIEWS IN silver LIKE '*metric*'"))